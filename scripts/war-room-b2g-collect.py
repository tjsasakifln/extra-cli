#!/usr/bin/env python3
"""war-room-b2g coletor — DataLake-first p/ dossie de UM edital.

Substitui 5 curls inline (Phase 1a + 1c + 3a + 3b + 4a) por 1 invocacao DataLake.
PDFs (Phase 1b) e leitura integral (Phase 2) permanecem live por design.

CLI aceita 3 formatos no posicional:
  - URL completa: https://pncp.gov.br/app/editais/13714142000162-1-000014/2026
  - Legacy: 13714142000162/2026/14
  - Raw pncp_id: 13714142000162-1-000014/2026

Resolucao de pncp_id (tri-step):
  1. Tenta candidate `{cnpj14}-1-{seq:06d}/{ano}` (Lei 14.133 mais comum) -> bid_detail
  2. Cache miss: search_bids janela do ano + filtra client-side por orgao+sequencial
  3. Ainda 0: fallback live PNCP /api/consulta/v1/contratacoes/publicacao?cnpj=...

CLI:
    python scripts/war-room-b2g-collect.py "13714142000162/2026/14" \\
        --cnpj 12345678000190 --preco-alvo 500000 \\
        --output docs/war-room/war-room-data-13714142000162-2026-14.json

Output JSON:
    {
      "fonte":"datalake|live","edital":{pncp_id, objeto, valor, datas, link_pncp,...},
      "perfil_empresa":{razao_social, cnae, sancoes:[]},
      "pricing_orgao":{n,p25,mediana,p75,sample:[]},
      "pricing_mercado":{n,p25,mediana,p75,sample:[]},
      "incumbentes":[{ni_fornecedor,nome,n_contratos,valor_total,ultimo}],
      "keywords":[...],"preco_alvo":850000,"preco_alvo_posicao":"P55",
      "warnings":[]
    }

PDFs (Phase 1b/2) NAO sao baixados aqui — caller (slash command) faz live com
curl + Read sobre /api/pncp/v1/orgaos/.../arquivos.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from datalake_helper import DatalakeClient  # noqa: E402


_PNCP_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
_OPENCNPJ_URL = "https://api.opencnpj.org/{cnpj}"

_STOPWORDS = {"de", "da", "do", "das", "dos", "para", "em", "no", "na", "nos", "nas",
              "e", "ou", "com", "por", "a", "o", "as", "os", "um", "uma", "que", "se"}


# ---------------------------------------------------------------------------
# pncp_id resolution
# ---------------------------------------------------------------------------

def parse_input(arg: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Retorna (cnpj_orgao, ano, sequencial, pncp_id_candidate)."""
    arg = arg.strip()
    # URL
    if arg.startswith("http"):
        m = re.search(r"/editais/([\w\-]+/\d{4})", arg)
        if m:
            return _split_pncp_id(m.group(1))
        # Tail mais agressivo (sem /editais/ explicito)
        tail = arg.rstrip("/").rsplit("/", 1)[-1]
        return _split_pncp_id(tail)
    # Legacy {cnpj}/{ano}/{seq}
    parts = arg.split("/")
    if len(parts) == 3 and parts[0].isdigit() and len(parts[0]) == 14 and parts[1].isdigit():
        cnpj, ano, seq = parts
        try:
            seq_int = int(seq)
        except ValueError:
            seq_int = 0
        return cnpj, ano, str(seq_int), f"{cnpj}-1-{seq_int:06d}/{ano}"
    # Raw pncp_id
    return _split_pncp_id(arg)


def _split_pncp_id(pid: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Split format `{cnpj14}-{n}-{seq:06d}/{ano}`."""
    m = re.match(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$", pid)
    if m:
        cnpj, _disp, seq, ano = m.group(1), m.group(2), m.group(3), m.group(4)
        return cnpj, ano, str(int(seq)), pid
    return None, None, None, pid if pid else None


def resolve_pncp_id(arg: str, dl: DatalakeClient) -> tuple[dict | None, str]:
    """Tri-step. Retorna (edital_dict, fonte_resolution)."""
    cnpj_orgao, ano, seq, pid_candidate = parse_input(arg)
    if pid_candidate:
        edital, _meta = dl.bid_detail(pid_candidate)
        if edital is not None:
            return edital, "bid_detail"

    # Step 2: search_bids window do ano + filtro client-side
    if cnpj_orgao and ano and seq:
        ds = f"{ano}-01-01"
        de = f"{ano}-12-31"
        rows, _ = dl.search_bids(
            date_start=ds, date_end=de,
            paginate_by_uf_modalidade=False,
            limit=5000,
        )
        rows = rows or []
        for r in rows:
            if (r.get("orgao_cnpj") == cnpj_orgao
                and r.get("pncp_id", "").endswith(f"/{ano}")
                and _seq_from_pncp_id(r["pncp_id"]) == int(seq)):
                return r, "search_bids_year"

    # Step 3: live PNCP fallback
    if cnpj_orgao and ano:
        live = _live_pncp_orgao_year(cnpj_orgao, ano, target_seq=int(seq) if seq else None)
        if live:
            return live, "live_pncp"

    return None, "not_found"


def _seq_from_pncp_id(pid: str) -> int | None:
    m = re.match(r"^\d{14}-\d+-(\d+)/\d{4}$", pid or "")
    return int(m.group(1)) if m else None


def _live_pncp_orgao_year(cnpj_orgao: str, ano: str, target_seq: int | None = None) -> dict | None:
    try:
        import httpx
    except ImportError:
        return None
    di = f"{ano}0101"
    df = date.today().strftime("%Y%m%d") if int(ano) >= date.today().year else f"{ano}1231"
    try:
        with httpx.Client(timeout=30.0) as client:
            for page in range(1, 11):
                r = client.get(_PNCP_URL, params={
                    "dataInicial": di, "dataFinal": df,
                    "cnpj": cnpj_orgao,
                    "pagina": page, "tamanhoPagina": 50,
                })
                if r.status_code == 204 or r.status_code >= 400:
                    break
                items = (r.json() or {}).get("data") or []
                if not items:
                    break
                for it in items:
                    pid = it.get("numeroControlePNCP")
                    if pid and (target_seq is None or _seq_from_pncp_id(pid) == target_seq):
                        return _pncp_to_normalized(it)
                if len(items) < 50:
                    break
                time.sleep(0.3)
    except Exception:
        return None
    return None


def _pncp_to_normalized(item: dict) -> dict:
    unidade = item.get("unidadeOrgao") or {}
    orgao = item.get("orgaoEntidade") or {}
    return {
        "pncp_id": item.get("numeroControlePNCP"),
        "objeto_compra": item.get("objetoCompra"),
        "valor_total_estimado": float(item.get("valorTotalEstimado") or 0),
        "uf": (unidade.get("ufSigla") or "").upper(),
        "municipio": unidade.get("municipioNome"),
        "codigo_municipio_ibge": unidade.get("codigoIbge"),
        "esfera_id": (orgao.get("esferaId") or "")[:1],
        "orgao_cnpj": orgao.get("cnpj"),
        "orgao_razao_social": orgao.get("razaoSocial"),
        "unidade_nome": unidade.get("nomeUnidade"),
        "modalidade_id": item.get("modalidadeId"),
        "modalidade_nome": item.get("modalidadeNome"),
        "data_publicacao": item.get("dataPublicacaoPncp"),
        "data_abertura": item.get("dataAberturaProposta"),
        "data_encerramento": item.get("dataEncerramentoProposta"),
        "situacao_compra": item.get("situacaoCompraNome"),
        "link_pncp": item.get("linkSistemaOrigem"),
        "link_sistema_origem": item.get("linkSistemaOrigem"),
    }


# ---------------------------------------------------------------------------
# Keyword extraction (do objeto)
# ---------------------------------------------------------------------------

def extract_keywords(objeto: str, cap: int = 6) -> list[str]:
    """Tokens significativos (>=4 chars, sem stopwords PT-BR)."""
    tokens = re.findall(r"[a-zà-úA-ZÀ-Ú]+", (objeto or "").lower())
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) < 4 or t in _STOPWORDS:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:cap]


# ---------------------------------------------------------------------------
# Empresa cliente — perfil
# ---------------------------------------------------------------------------

def collect_perfil_empresa(cnpj14: str, dl: DatalakeClient) -> dict | None:
    if cnpj14 and len(cnpj14) == 14:
        if dl.is_enabled:
            data, _ = dl.enriched_entity("fornecedor", cnpj14)
            if isinstance(data, dict):
                return data
        # cache miss → live OpenCNPJ
        try:
            import httpx
            with httpx.Client(timeout=15.0) as client:
                r = client.get(_OPENCNPJ_URL.format(cnpj=cnpj14))
                if r.status_code == 200:
                    return r.json()
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Preco alvo positioning
# ---------------------------------------------------------------------------

def position_preco_alvo(preco_alvo: float, stats: dict | None) -> dict:
    if not stats or preco_alvo is None or preco_alvo <= 0:
        return {"posicao": None, "alerta": None}
    sample_vals = sorted(float(c.get("valor_global") or 0) for c in stats.get("sample", []))
    sample_vals = [v for v in sample_vals if v > 0]
    if not sample_vals:
        return {"posicao": None, "alerta": "sem amostra para comparar"}
    n = len(sample_vals)
    pos = sum(1 for v in sample_vals if v < preco_alvo) / n * 100
    alerta = None
    p10 = stats.get("p10", 0)
    p90 = stats.get("p90", 0)
    if preco_alvo < p10:
        alerta = "ABAIXO_P10_inexequibilidade_potencial"
    elif preco_alvo > p90:
        alerta = "ACIMA_P90_risco_de_perder"
    return {
        "posicao": f"P{round(pos)}",
        "posicao_pct": round(pos, 1),
        "alerta": alerta,
        "p10": p10, "p90": p90,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="War-Room B2G — DataLake-first")
    ap.add_argument("edital", help="URL PNCP, '{cnpj}/{ano}/{seq}' ou pncp_id raw")
    ap.add_argument("--cnpj", help="CNPJ da empresa que vai participar")
    ap.add_argument("--preco-alvo", type=float, help="Preco que o cliente pretende ofertar")
    ap.add_argument("--no-datalake", action="store_true", help="Forca fallback live")
    ap.add_argument("--no-pdfs", action="store_true", help="Pula download PDFs (Claude faz Phase 1b)")
    ap.add_argument("--output", required=True, help="JSON de saida")
    args = ap.parse_args()

    dl = DatalakeClient()
    use_dl = (not args.no_datalake) and os.getenv("DATALAKE_QUERY_ENABLED", "").lower() in ("true", "1") and dl.is_enabled

    if not use_dl:
        print("AVISO: DataLake desabilitado — apenas resolucao live.", file=sys.stderr)

    print(f"[war-room] edital={args.edital!r} cnpj={args.cnpj} preco_alvo={args.preco_alvo}")
    t = time.time()
    edital, fonte_res = (resolve_pncp_id(args.edital, dl) if use_dl
                         else (_resolve_live_only(args.edital), "live_only"))
    print(f"  resolucao={fonte_res} em {time.time()-t:.1f}s")
    if edital is None:
        print(f"ERRO: edital nao encontrado ({args.edital})", file=sys.stderr)
        return 1

    cnpj_orgao = edital.get("orgao_cnpj")
    uf_edital = edital.get("uf")
    keywords = extract_keywords(edital.get("objeto_compra") or "")
    print(f"  edital: {edital.get('objeto_compra','')[:80]}")
    print(f"    orgao={cnpj_orgao} uf={uf_edital} valor={edital.get('valor_total_estimado')}")
    print(f"    keywords={keywords}")

    perfil_empresa = None
    if args.cnpj:
        cnpj14 = "".join(ch for ch in args.cnpj if ch.isdigit())
        if len(cnpj14) == 14:
            perfil_empresa = collect_perfil_empresa(cnpj14, dl)

    pricing_orgao = None
    pricing_mercado = None
    incumbentes: list[dict] = []
    warnings: list[str] = []

    if use_dl and keywords:
        # Pricing do orgao
        po, m_po = dl.pricing_stats(keywords=keywords, orgao_cnpj=cnpj_orgao, meses=24)
        pricing_orgao = po
        if po is None:
            warnings.append(f"pricing_orgao: {m_po.get('datalake_error','sem dados')}")
        # Pricing do mercado regional
        pm, m_pm = dl.pricing_stats(keywords=keywords, ufs=[uf_edital] if uf_edital else None, meses=24)
        pricing_mercado = pm
        if pm is None:
            warnings.append(f"pricing_mercado: {m_pm.get('datalake_error','sem dados')}")
        # Top competitors do orgao
        comps, _ = dl.top_competitors(orgao_cnpj=cnpj_orgao, setor_keywords=keywords, meses=24, limit=10)
        incumbentes = comps or []
        if not incumbentes:
            # Fallback sem keywords (qualquer fornecedor do orgao)
            comps2, _ = dl.top_competitors(orgao_cnpj=cnpj_orgao, meses=24, limit=10)
            incumbentes = comps2 or []
            if incumbentes:
                warnings.append("incumbentes: usados todos os fornecedores do orgao (sem filtro setor)")
    elif not keywords:
        warnings.append("keywords vazias — pricing/incumbentes pulados")

    preco_alvo_info = {"posicao": None}
    if args.preco_alvo and pricing_orgao:
        preco_alvo_info = position_preco_alvo(args.preco_alvo, pricing_orgao)
    elif args.preco_alvo and pricing_mercado:
        preco_alvo_info = position_preco_alvo(args.preco_alvo, pricing_mercado)

    payload = {
        "fonte": "datalake" if use_dl else "live",
        "fonte_resolucao": fonte_res,
        "edital": edital,
        "perfil_empresa": perfil_empresa,
        "pricing_orgao": _strip_sample(pricing_orgao, keep_top=20),
        "pricing_mercado": _strip_sample(pricing_mercado, keep_top=20),
        "incumbentes": incumbentes,
        "keywords": keywords,
        "preco_alvo": args.preco_alvo,
        "preco_alvo_info": preco_alvo_info,
        "warnings": warnings,
        "no_pdfs": args.no_pdfs,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  pricing_orgao_n={(pricing_orgao or {}).get('n',0)} | "
          f"pricing_mercado_n={(pricing_mercado or {}).get('n',0)} | "
          f"incumbentes={len(incumbentes)} | warnings={len(warnings)}")
    print(f"  Output: {out_path}")
    return 0


def _strip_sample(stats: dict | None, keep_top: int = 20) -> dict | None:
    if not stats:
        return None
    out = dict(stats)
    if "sample" in out and isinstance(out["sample"], list):
        out["sample"] = out["sample"][:keep_top]
    return out


def _resolve_live_only(arg: str) -> dict | None:
    cnpj_orgao, ano, seq, _ = parse_input(arg)
    if not (cnpj_orgao and ano):
        return None
    return _live_pncp_orgao_year(cnpj_orgao, ano, target_seq=int(seq) if seq else None)


if __name__ == "__main__":
    raise SystemExit(main())
