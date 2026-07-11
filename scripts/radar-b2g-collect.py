#!/usr/bin/env python3
"""radar-b2g coletor — varredura DataLake-first de novos editais B2G.

Substitui paginação curl PNCP (Phase 2a) por `DatalakeClient.search_bids()`
(via RPC `search_datalake`, paginated por UF×modalidade). Latência <30s vs
~5-10min do live em dia típico (~108 RPCs vs ~108 curls com throttle).

Modo híbrido: se ETL pncp_raw_bids tem gap >30min vs NOW, complementa com 1 curl
PNCP cobrindo `[last_etl_at, NOW()]` — garante freshness do dia.

NÃO MIGRADO (continuam live, são executados pelo Claude downstream):
  - PCP v2 (Phase 2b): API externa, não ingerida no DataLake
  - PDFs do edital (Phase 3): metadata + binários ficam live por design

CLI:
    python scripts/radar-b2g-collect.py \\
        --carteira docs/carteira-clientes.json \\
        --dias 1 \\
        --output docs/radar/radar-data-2026-04-29.json

    python scripts/radar-b2g-collect.py \\
        --cnpj 12345678000190 \\
        --setor medicamentos \\
        --dias 1 \\
        --output docs/radar/radar-data-12345678000190-2026-04-29.json

Output JSON (consumido pelas Phases 3-5 do command):
    {
      "fonte": "datalake|datalake_hybrid|live",
      "data_referencia": "2026-04-29",
      "dias": 1,
      "carteira": [{cnpj, nome_fantasia, setor, keywords, ufs_interesse, valor_min, valor_max}, ...],
      "editais": [{pncp_id, objeto_compra, valor_total_estimado, uf, municipio,
                   orgao_cnpj, orgao_razao_social, modalidade_id, modalidade_nome,
                   data_publicacao, data_encerramento, link_pncp}, ...],
      "matching": [{cnpj_cliente, edital_pncp_id, score, tag,
                    dimensions: {keywords, valor, geografia, prazo, habilitacao}}, ...],
      "etl_gap_min": 14,
      "warnings": [...],
      "generated_at": "2026-04-29T06:00:00"
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from datalake_helper import DatalakeClient  # noqa: E402


_DEFAULT_MODALIDADES = [4, 5, 6, 8]
_DEFAULT_VALOR_MIN = 0
_DEFAULT_VALOR_MAX = 10_000_000_000  # 10B = "no cap"
_HYBRID_GAP_MIN = 30  # minutos: se ETL atrasou mais que isso, complementar com live


# ---------------------------------------------------------------------------
# Sectors data
# ---------------------------------------------------------------------------

def load_sectors() -> dict:
    """Lê backend/sectors_data.yaml (estrutura {sectors: {setor_id: {...}}})."""
    repo_root = Path(__file__).parent.parent
    path = repo_root / "backend" / "sectors_data.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sectors", data) if isinstance(data, dict) else {}


def resolve_keywords(setor: str, keywords_extras: list[str] | None, sectors: dict) -> list[str]:
    """Retorna keywords do setor + extras, deduplicadas em minúsculas."""
    seen: set[str] = set()
    out: list[str] = []
    if setor and setor in sectors:
        for k in sectors[setor].get("keywords", []):
            kk = k.lower().strip()
            if kk and kk not in seen:
                seen.add(kk)
                out.append(kk)
    for k in keywords_extras or []:
        kk = k.lower().strip()
        if kk and kk not in seen:
            seen.add(kk)
            out.append(kk)
    return out


def resolve_value_range(
    cliente: dict, setor: str, sectors: dict
) -> tuple[float, float]:
    if cliente.get("valor_min") is not None and cliente.get("valor_max") is not None:
        return float(cliente["valor_min"]), float(cliente["valor_max"])
    if setor in sectors:
        rng = sectors[setor].get("viability_value_range")
        if rng and len(rng) == 2:
            return float(rng[0]), float(rng[1])
    return float(_DEFAULT_VALOR_MIN), float(_DEFAULT_VALOR_MAX)


# ---------------------------------------------------------------------------
# Carteira loading
# ---------------------------------------------------------------------------

def load_carteira(args: argparse.Namespace, sectors: dict) -> list[dict]:
    """Constrói carteira normalizada a partir dos args.

    Cada cliente fica com: cnpj, nome_fantasia, setor, keywords (resolved),
    ufs_interesse, valor_min, valor_max, modalidades.
    """
    raw_clientes: list[dict] = []
    if args.carteira:
        path = Path(args.carteira)
        if not path.exists():
            print(f"ERRO: carteira não encontrada: {path}", file=sys.stderr)
            sys.exit(2)
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_clientes = data.get("clientes") or []
    elif args.cnpj:
        raw_clientes = [
            {
                "cnpj": "".join(ch for ch in args.cnpj if ch.isdigit()),
                "nome_fantasia": args.cnpj,
                "setor": args.setor or "",
                "ufs_interesse": [u.strip().upper() for u in (args.uf or "").split(",") if u.strip()],
            }
        ]
    elif args.setor:
        raw_clientes = [
            {
                "cnpj": "",
                "nome_fantasia": f"setor:{args.setor}",
                "setor": args.setor,
                "ufs_interesse": [u.strip().upper() for u in (args.uf or "").split(",") if u.strip()],
            }
        ]
    else:
        print("ERRO: forneça --carteira, --cnpj ou --setor.", file=sys.stderr)
        sys.exit(2)

    out: list[dict] = []
    for c in raw_clientes:
        setor = c.get("setor") or ""
        keywords = resolve_keywords(setor, c.get("keywords_extras") or [], sectors)
        vmin, vmax = resolve_value_range(c, setor, sectors)
        out.append({
            "cnpj": "".join(ch for ch in (c.get("cnpj") or "") if ch.isdigit()),
            "nome_fantasia": c.get("nome_fantasia") or c.get("razao_social") or "",
            "setor": setor,
            "keywords": keywords,
            "ufs_interesse": [u.upper() for u in (c.get("ufs_interesse") or [])],
            "valor_min": vmin,
            "valor_max": vmax,
            "modalidades": c.get("modalidades") or list(_DEFAULT_MODALIDADES),
            "porte": c.get("porte") or "",
            "capital_social": c.get("capital_social") or 0,
            "pacote": c.get("pacote") or "",
            "decisor": c.get("decisor") or "",
        })
    return out


# ---------------------------------------------------------------------------
# DataLake collector
# ---------------------------------------------------------------------------

def collect_from_datalake(
    carteira: list[dict],
    dias: int,
    urgente: bool,
    valor_min_global: float | None = None,
    valor_max_global: float | None = None,
) -> dict:
    dl = DatalakeClient()
    if not dl.is_enabled:
        return {"error": dl.init_error or "DATALAKE_QUERY_ENABLED=false", "fonte": "datalake_disabled"}

    # Consolidar UFs (set; vazio = todas)
    all_ufs = sorted({u for c in carteira for u in c["ufs_interesse"]})
    # Consolidar keywords (OR-tsquery)
    all_kws = sorted({k for c in carteira for k in c["keywords"]})
    # Consolidar modalidades
    all_mods = sorted({m for c in carteira for m in c["modalidades"]}) or list(_DEFAULT_MODALIDADES)

    tsquery = " | ".join(_tsquery_token(k) for k in all_kws) if all_kws else None
    modo = "abertas" if urgente else "publicacao"

    rows, meta = dl.search_bids(
        ufs=all_ufs or None,
        dias=dias,
        tsquery=tsquery,
        modalidades=all_mods,
        modo=modo,
        valor_min=valor_min_global,
        valor_max=valor_max_global,
        paginate_by_uf_modalidade=bool(all_ufs and all_mods),
        limit=2000,
    )
    if rows is None:
        return {"error": meta.get("datalake_error", "unknown"), "fonte": "datalake_failed", "meta": meta}

    # Hybrid: complementar com live se ETL atrasou
    last_etl, etl_meta = dl.last_etl_at()
    etl_gap_min: float | None = None
    bids_live_complement: list[dict] = []
    if last_etl is not None:
        gap = datetime.now(timezone.utc) - last_etl
        etl_gap_min = round(gap.total_seconds() / 60, 1)
        if etl_gap_min > _HYBRID_GAP_MIN and modo != "abertas":
            bids_live_complement = _live_pncp_window(
                start=last_etl,
                end=datetime.now(timezone.utc),
                modalidades=all_mods,
            )

    bids_all = list(rows)
    seen_ids = {r.get("pncp_id") for r in bids_all}
    for b in bids_live_complement:
        if b.get("pncp_id") and b["pncp_id"] not in seen_ids:
            bids_all.append(b)
            seen_ids.add(b["pncp_id"])

    fonte = "datalake_hybrid" if bids_live_complement else "datalake"

    return {
        "fonte": fonte,
        "editais": _normalize_editais(bids_all),
        "etl_gap_min": etl_gap_min,
        "etl_meta": etl_meta,
        "live_complement_added": len(bids_live_complement),
        "meta": meta,
    }


def _tsquery_token(kw: str) -> str:
    """Sanitiza keyword p/ tsquery (escape espaços + caracteres especiais)."""
    safe = "".join(ch if (ch.isalnum() or ch == "-") else " " for ch in kw)
    parts = [p for p in safe.split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + " & ".join(parts) + ")"


def _normalize_editais(bids: list[dict]) -> list[dict]:
    """Normaliza shape das rows do DataLake para output JSON estável."""
    out = []
    for b in bids:
        out.append({
            "pncp_id": b.get("pncp_id"),
            "objeto_compra": b.get("objeto_compra"),
            "valor_total_estimado": b.get("valor_total_estimado") or 0,
            "uf": b.get("uf"),
            "municipio": b.get("municipio"),
            "codigo_municipio_ibge": b.get("codigo_municipio_ibge"),
            "esfera_id": b.get("esfera_id"),
            "orgao_cnpj": b.get("orgao_cnpj"),
            "orgao_razao_social": b.get("orgao_razao_social"),
            "unidade_nome": b.get("unidade_nome"),
            "modalidade_id": b.get("modalidade_id"),
            "modalidade_nome": b.get("modalidade_nome"),
            "data_publicacao": b.get("data_publicacao"),
            "data_abertura": b.get("data_abertura"),
            "data_encerramento": b.get("data_encerramento"),
            "situacao_compra": b.get("situacao_compra"),
            "link_pncp": b.get("link_pncp"),
            "link_sistema_origem": b.get("link_sistema_origem"),
        })
    return out


# ---------------------------------------------------------------------------
# Live PNCP fallback / hybrid complement
# ---------------------------------------------------------------------------

_PNCP_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"


def _live_pncp_window(
    start: datetime,
    end: datetime,
    modalidades: list[int],
    max_pages_per_mod: int = 5,
) -> list[dict]:
    """1 curl rápido por modalidade no janela [start, end] (modo híbrido)."""
    try:
        import httpx
    except ImportError:
        return []

    di = start.strftime("%Y%m%d")
    df = end.strftime("%Y%m%d")
    out: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        for mod_id in modalidades:
            for page in range(1, max_pages_per_mod + 1):
                try:
                    r = client.get(_PNCP_URL, params={
                        "dataInicial": di, "dataFinal": df,
                        "codigoModalidadeContratacao": mod_id,
                        "pagina": page, "tamanhoPagina": 50,
                    })
                    if r.status_code == 204 or r.status_code >= 400:
                        break
                    items = (r.json() or {}).get("data") or []
                    if not items:
                        break
                    for it in items:
                        out.append(_pncp_to_normalized(it))
                    if len(items) < 50:
                        break
                except Exception:
                    break
                time.sleep(0.3)
    return out


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
# Live full fallback (preserva fluxo legado quando DataLake desabilitado)
# ---------------------------------------------------------------------------

def collect_from_live(
    carteira: list[dict],
    dias: int,
    urgente: bool,
) -> dict:
    """Fallback live: paginação PNCP por modalidade × dias."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        return {"error": "httpx required for live fallback", "fonte": "live_failed"}

    today = date.today()
    start = today - timedelta(days=dias)
    end = today
    all_mods = sorted({m for c in carteira for m in c["modalidades"]}) or list(_DEFAULT_MODALIDADES)

    bids = _live_pncp_window(
        start=datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
        end=datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
        modalidades=all_mods,
        max_pages_per_mod=20,
    )
    return {
        "fonte": "live",
        "editais": bids,
        "etl_gap_min": None,
        "live_complement_added": 0,
        "meta": {"modalidades": all_mods, "dias": dias},
    }


# ---------------------------------------------------------------------------
# Matching cliente × edital
# ---------------------------------------------------------------------------

def score_matching(cliente: dict, edital: dict, hoje: date) -> dict:
    """Calcula score 0-100 + breakdown por dimensão.

    Pesos (do .md original):
      keywords 30 | valor 20 | geo 20 | prazo 15 | habilitacao 15
    """
    objeto = (edital.get("objeto_compra") or "").lower()
    kws = cliente.get("keywords") or []
    matched = sum(1 for k in kws if k in objeto)
    kw_density = (matched / max(len(kws), 1)) * 100 if kws else 0
    kw_score = round(min(kw_density / 100 * 30, 30), 1)

    valor = float(edital.get("valor_total_estimado") or 0)
    vmin = cliente.get("valor_min") or 0
    vmax = cliente.get("valor_max") or _DEFAULT_VALOR_MAX
    if valor <= 0:
        valor_score = 10  # neutro: sem valor divulgado, não penaliza nem premia
    elif vmin <= valor <= vmax:
        valor_score = 20
    elif valor < vmin and valor >= vmin * 0.5:
        valor_score = 12
    elif valor > vmax and valor <= vmax * 1.5:
        valor_score = 12
    else:
        valor_score = 0

    uf_edital = edital.get("uf") or ""
    ufs = cliente.get("ufs_interesse") or []
    if not ufs:
        geo_score = 15  # cliente aceita qualquer UF
    elif uf_edital in ufs:
        geo_score = 20
    else:
        geo_score = 0

    enc = edital.get("data_encerramento")
    prazo_score = 15
    if enc:
        try:
            enc_dt = datetime.fromisoformat(enc.replace("Z", "+00:00")).date()
            dias_restantes = (enc_dt - hoje).days
            if dias_restantes < 0:
                prazo_score = 0
            elif dias_restantes <= 3:
                prazo_score = 4
            elif dias_restantes <= 7:
                prazo_score = 9
            elif dias_restantes <= 15:
                prazo_score = 13
            else:
                prazo_score = 15
        except (ValueError, TypeError):
            prazo_score = 8

    capital = float(cliente.get("capital_social") or 0)
    if capital > 0 and valor > 0:
        # heurística: precisa ter capital ~10% do valor estimado
        ratio = capital / valor
        if ratio >= 0.10:
            hab_score = 15
        elif ratio >= 0.05:
            hab_score = 10
        else:
            hab_score = 5
    else:
        hab_score = 10  # neutro se sem dado

    total = round(kw_score + valor_score + geo_score + prazo_score + hab_score, 1)
    if total >= 80:
        tag = "QUENTE"
    elif total >= 60:
        tag = "MORNO"
    elif total >= 40:
        tag = "FRIO"
    else:
        tag = "DESCARTADO"

    return {
        "score": total,
        "tag": tag,
        "dimensions": {
            "keywords": kw_score,
            "valor": valor_score,
            "geografia": geo_score,
            "prazo": prazo_score,
            "habilitacao": hab_score,
        },
    }


def build_matching(carteira: list[dict], editais: list[dict]) -> list[dict]:
    hoje = date.today()
    out: list[dict] = []
    for cliente in carteira:
        if not cliente["cnpj"] and not cliente.get("nome_fantasia"):
            continue
        for edital in editais:
            sc = score_matching(cliente, edital, hoje)
            if sc["tag"] == "DESCARTADO":
                continue
            out.append({
                "cnpj_cliente": cliente["cnpj"],
                "nome_cliente": cliente["nome_fantasia"],
                "edital_pncp_id": edital["pncp_id"],
                "score": sc["score"],
                "tag": sc["tag"],
                "dimensions": sc["dimensions"],
            })
    out.sort(key=lambda m: m["score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Radar B2G — varredura DataLake-first")
    ap.add_argument("--carteira", help="Caminho do JSON de carteira de clientes")
    ap.add_argument("--cnpj", help="CNPJ único (sem carteira)")
    ap.add_argument("--setor", help="Setor único (sem carteira/cnpj)")
    ap.add_argument("--uf", default="", help="UFs CSV (apenas se --cnpj/--setor sem carteira)")
    ap.add_argument("--dias", type=int, default=1, help="Janela em dias (default 1)")
    ap.add_argument("--urgente", action="store_true", help="modo='abertas' (encerramento futuro)")
    ap.add_argument("--no-datalake", action="store_true", help="Forçar fallback live")
    ap.add_argument("--no-pcp", action="store_true", help="Pula PCP v2 (relevante apenas em fluxo live downstream)")
    ap.add_argument("--no-pdfs", action="store_true", help="Pula download PDFs (downstream Phase 3)")
    ap.add_argument("--output", required=True, help="Caminho do JSON de saída")
    args = ap.parse_args()

    sectors = load_sectors()
    if not sectors:
        print("AVISO: backend/sectors_data.yaml não disponível — usando apenas keywords_extras", file=sys.stderr)

    carteira = load_carteira(args, sectors)
    print(f"[radar-b2g] carteira={len(carteira)} clientes dias={args.dias} urgente={args.urgente}")
    for c in carteira:
        print(f"  - {c['cnpj'] or '(sem cnpj)'} | {c['nome_fantasia'][:40]} | setor={c['setor']} | "
              f"ufs={c['ufs_interesse']} | n_kw={len(c['keywords'])}")

    result: dict | None = None
    use_dl = (not args.no_datalake) and os.getenv("DATALAKE_QUERY_ENABLED", "").lower() in ("true", "1")

    if use_dl:
        print("  Tentando DataLake...")
        t = time.time()
        dl_result = collect_from_datalake(carteira, args.dias, args.urgente)
        dt = time.time() - t
        if dl_result.get("error"):
            print(f"  DataLake falhou ({dl_result['error']}). Caindo em fallback live...")
        else:
            result = dl_result
            print(f"  DataLake OK em {dt:.1f}s — {len(result['editais'])} editais "
                  f"(gap_etl={result.get('etl_gap_min')}min, hybrid_added={result.get('live_complement_added')})")

    if result is None:
        print("  Buscando live PNCP...")
        t = time.time()
        result = collect_from_live(carteira, args.dias, args.urgente)
        dt = time.time() - t
        if result.get("error"):
            print(f"  Live falhou: {result['error']}", file=sys.stderr)
            return 1
        print(f"  Live OK em {dt:.1f}s — {len(result['editais'])} editais")

    matching = build_matching(carteira, result["editais"])
    print(f"  Matching: {len(matching)} pares cliente×edital "
          f"(QUENTE={sum(1 for m in matching if m['tag']=='QUENTE')}, "
          f"MORNO={sum(1 for m in matching if m['tag']=='MORNO')})")

    payload = {
        "fonte": result["fonte"],
        "data_referencia": date.today().strftime("%Y-%m-%d"),
        "dias": args.dias,
        "urgente": args.urgente,
        "carteira": carteira,
        "editais": result["editais"],
        "matching": matching,
        "etl_gap_min": result.get("etl_gap_min"),
        "live_complement_added": result.get("live_complement_added", 0),
        "warnings": [],
        "meta": result.get("meta", {}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if args.no_pcp:
        payload["warnings"].append("PCP v2 ignorado (--no-pcp)")
    if args.no_pdfs:
        payload["warnings"].append("Download PDFs ignorado (--no-pdfs)")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
