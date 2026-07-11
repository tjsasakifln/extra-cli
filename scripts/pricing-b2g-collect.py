#!/usr/bin/env python3
"""pricing-b2g coletor — análise estatística de preços B2G.

Pilot do refactor DataLake-first (plano `temos-commands-como-intel-b2g-sunny-minsky`).
Substitui paginação curl PNCP (~2-5min) por query agregada em `pncp_supplier_contracts`
via `DatalakeClient.pricing_stats()` (<5s).

Fallback: se DATALAKE_QUERY_ENABLED=false OU --no-datalake OU DataLake falha,
cai em paginação live PNCP API (preserva fluxo legado do command).

CLI:
    python scripts/pricing-b2g-collect.py \\
        --objeto "limpeza hospitalar" \\
        --uf SP,MG \\
        --meses 12 \\
        --output docs/pricing/pricing-limpeza-hospitalar-2026-04-29.json

Output JSON (consumido por etapa de geração de XLSX/relatório):
    {
        "objeto": "limpeza hospitalar",
        "keywords_used": ["limpeza", "hospitalar"],
        "ufs": ["SP","MG"],
        "meses": 12,
        "fonte": "datalake" | "live",
        "stats": {n, p10, p25, mediana, p75, p90, media, dp, cv},
        "sample": [{...top contratos...}],
        "warnings": [...],
        "generated_at": "2026-04-29T..."
    }

Caveat documentado:
    `pncp_supplier_contracts.valor_global` é populado por cascade do crawler:
    valorGlobal → valorInicial → valorTotalEstimado (backend/ingestion/contracts_crawler.py:191-218).
    Mesma semântica que `valorTotalHomologado || valorTotalEstimado` da API live.
    Sem distinção formal homologado-puro vs estimado-fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Permite import de datalake_helper irmão
sys.path.insert(0, str(Path(__file__).parent))

from datalake_helper import DatalakeClient  # noqa: E402


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "em", "no", "na", "nos", "nas",
    "e", "ou", "com", "por", "a", "o", "as", "os", "um", "uma", "que", "se",
    "the", "of", "and",
}


def extract_keywords(objeto: str) -> list[str]:
    """Quebra objeto em tokens significativos (>=4 chars, sem stopwords)."""
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
    return out[:8]  # cap em 8 keywords (suficiente para FTS/ILIKE)


# ---------------------------------------------------------------------------
# DataLake-first collector
# ---------------------------------------------------------------------------

def collect_from_datalake(
    objeto: str,
    keywords: list[str],
    ufs: list[str] | None,
    meses: int,
    orgao_cnpj: str | None,
    valor_min: float,
) -> dict:
    """Coleta + agrega via `DatalakeClient.pricing_stats()`."""
    dl = DatalakeClient()
    if not dl.is_enabled:
        return {"error": dl.init_error or "DATALAKE_QUERY_ENABLED=false", "fonte": "datalake_disabled"}

    stats, meta = dl.pricing_stats(
        keywords=keywords,
        ufs=ufs,
        meses=meses,
        orgao_cnpj=orgao_cnpj,
        valor_min=valor_min,
    )
    if stats is None:
        return {"error": meta.get("datalake_error", "unknown"), "fonte": "datalake_failed", "meta": meta}

    sample = stats.pop("sample", [])
    return {
        "fonte": "datalake",
        "keywords_used": keywords,
        "stats": stats,
        "sample": [
            {
                "numero_controle_pncp": r.get("numero_controle_pncp"),
                "ni_fornecedor": r.get("ni_fornecedor"),
                "nome_fornecedor": r.get("nome_fornecedor"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "orgao_nome": r.get("orgao_nome"),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
                "esfera": r.get("esfera"),
                "valor_global": r.get("valor_global"),
                "data_assinatura": r.get("data_assinatura"),
                "objeto_contrato": r.get("objeto_contrato"),
            }
            for r in sample[:200]
        ],
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# Live PNCP fallback (preserva fluxo legado do command)
# ---------------------------------------------------------------------------

_PNCP_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
_DEFAULT_MODALIDADES = [4, 5, 6, 8]


def collect_from_live(
    objeto: str,
    keywords: list[str],
    ufs: list[str] | None,
    meses: int,
    modalidades: list[int],
    valor_min: float,
    max_pages_per_mod: int = 20,
) -> dict:
    """Fallback live: pagina PNCP API por modalidade, filtra client-side."""
    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed for live fallback", "fonte": "live_failed"}

    data_fim = date.today()
    data_ini = data_fim - timedelta(days=int(meses * 30.4))
    di = data_ini.strftime("%Y%m%d")
    df = data_fim.strftime("%Y%m%d")

    kws_lower = [k.lower() for k in keywords]
    ufs_upper = {u.upper() for u in (ufs or [])}

    matches: list[dict] = []
    pages_fetched = 0
    errors: list[str] = []

    with httpx.Client(timeout=30.0) as client:
        for mod_id in modalidades:
            for page in range(1, max_pages_per_mod + 1):
                try:
                    r = client.get(
                        _PNCP_URL,
                        params={
                            "dataInicial": di,
                            "dataFinal": df,
                            "codigoModalidadeContratacao": mod_id,
                            "pagina": page,
                            "tamanhoPagina": 50,
                        },
                    )
                    pages_fetched += 1
                    if r.status_code == 204:
                        break
                    if r.status_code >= 400:
                        errors.append(f"mod{mod_id}/p{page}: HTTP {r.status_code}")
                        break
                    payload = r.json()
                    items = payload.get("data") or []
                    if not items:
                        break
                    for it in items:
                        valor = it.get("valorTotalHomologado") or it.get("valorTotalEstimado")
                        if valor is None:
                            continue
                        try:
                            v = float(valor)
                        except (ValueError, TypeError):
                            continue
                        if v < valor_min:
                            continue
                        objeto_compra = (it.get("objetoCompra") or "").lower()
                        if kws_lower and not any(k in objeto_compra for k in kws_lower):
                            continue
                        unidade = it.get("unidadeOrgao") or {}
                        uf = (unidade.get("ufSigla") or "").upper()
                        if ufs_upper and uf not in ufs_upper:
                            continue
                        orgao = it.get("orgaoEntidade") or {}
                        matches.append({
                            "numero_controle_pncp": it.get("numeroControlePNCP"),
                            "orgao_cnpj": orgao.get("cnpj"),
                            "orgao_nome": orgao.get("razaoSocial"),
                            "uf": uf,
                            "municipio": unidade.get("municipioNome"),
                            "esfera": (orgao.get("esferaId") or "")[:1],
                            "valor_global": round(v, 2),
                            "data_assinatura": it.get("dataPublicacaoPncp"),
                            "objeto_contrato": (it.get("objetoCompra") or "")[:500],
                            "_homologado": it.get("valorTotalHomologado") is not None,
                        })
                    if len(items) < 50:
                        break
                    time.sleep(0.5)  # polidez com a API PNCP
                except httpx.HTTPError as e:
                    errors.append(f"mod{mod_id}/p{page}: {e}")
                    break

    if not matches:
        return {
            "error": f"0 contracts matched (live; {pages_fetched} pages, {len(errors)} errors)",
            "fonte": "live_empty",
            "errors": errors,
        }

    valores = sorted(m["valor_global"] for m in matches)
    n = len(valores)
    media = sum(valores) / n
    var = sum((v - media) ** 2 for v in valores) / n
    dp = var ** 0.5
    cv = (dp / media * 100) if media > 0 else 0.0

    def percentile(p: float) -> float:
        if n == 1:
            return valores[0]
        k = (n - 1) * p
        f = int(k)
        c = min(f + 1, n - 1)
        if f == c:
            return valores[f]
        return valores[f] + (valores[c] - valores[f]) * (k - f)

    return {
        "fonte": "live",
        "keywords_used": keywords,
        "stats": {
            "n": n,
            "p10": round(percentile(0.10), 2),
            "p25": round(percentile(0.25), 2),
            "mediana": round(percentile(0.50), 2),
            "p75": round(percentile(0.75), 2),
            "p90": round(percentile(0.90), 2),
            "media": round(media, 2),
            "dp": round(dp, 2),
            "cv": round(cv, 2),
        },
        "sample": matches[:200],
        "meta": {
            "pages_fetched": pages_fetched,
            "errors": errors,
            "modalidades": modalidades,
        },
    }


# ---------------------------------------------------------------------------
# Confiability label (mesma escala do .md)
# ---------------------------------------------------------------------------

def confiability(n: int, cv: float | None = None) -> str:
    """Confiabilidade considera N e CV.

    CV alto (>200%) = matching produziu amostra heterogênea (ex: keyword genérica
    capturou contratos não-comparáveis). Mesmo com N alto, a estatística não é
    representativa — rebaixar para evitar recomendação de preço inexequível.
    """
    if cv is not None and cv > 200.0:
        return "AMOSTRA_HETEROGENEA"  # CV alto = não confiar em mediana
    if n > 50:
        return "ALTA"
    if n >= 20:
        return "MEDIA"
    if n >= 10:
        return "BAIXA"
    return "INSUFICIENTE"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Pricing B2G — análise estatística DataLake-first")
    ap.add_argument("--objeto", required=True, help='Objeto pesquisado (ex: "limpeza hospitalar")')
    ap.add_argument("--uf", default="", help="UFs separadas por vírgula (ex: SP,MG)")
    ap.add_argument("--meses", type=int, default=12, help="Janela em meses (default 12)")
    ap.add_argument("--cnpj-orgao", default=None, help="Filtrar por CNPJ do órgão")
    ap.add_argument(
        "--modalidade",
        default="",
        help="IDs de modalidade separados por vírgula (only live; default 4,5,6,8)",
    )
    ap.add_argument(
        "--no-datalake",
        action="store_true",
        help="Forçar fallback live (ignorar DataLake mesmo se DATALAKE_QUERY_ENABLED=true)",
    )
    ap.add_argument("--valor-min", type=float, default=1.0, help="Piso valor (default 1.0)")
    ap.add_argument("--output", required=True, help="Caminho do JSON de saída")
    args = ap.parse_args()

    ufs = [u.strip().upper() for u in args.uf.split(",") if u.strip()] or None
    modalidades = (
        [int(m) for m in args.modalidade.split(",") if m.strip()]
        if args.modalidade
        else _DEFAULT_MODALIDADES
    )
    keywords = extract_keywords(args.objeto)
    if not keywords:
        print("ERRO: --objeto não produziu keywords úteis.", file=sys.stderr)
        return 2

    print(f"[pricing-b2g] objeto={args.objeto!r} ufs={ufs} meses={args.meses}")
    print(f"  keywords: {keywords}")

    result: dict | None = None
    fonte: str = ""

    if not args.no_datalake and os.getenv("DATALAKE_QUERY_ENABLED", "").lower() in ("true", "1"):
        print("  Tentando DataLake...")
        dl_result = collect_from_datalake(
            objeto=args.objeto,
            keywords=keywords,
            ufs=ufs,
            meses=args.meses,
            orgao_cnpj=args.cnpj_orgao,
            valor_min=args.valor_min,
        )
        if dl_result.get("error"):
            print(f"  DataLake falhou: {dl_result['error']}. Caindo em fallback live...")
        else:
            result = dl_result
            fonte = "datalake"

    if result is None:
        print("  Buscando live PNCP API...")
        live_result = collect_from_live(
            objeto=args.objeto,
            keywords=keywords,
            ufs=ufs,
            meses=args.meses,
            modalidades=modalidades,
            valor_min=args.valor_min,
        )
        if live_result.get("error"):
            print(f"  Live falhou: {live_result['error']}", file=sys.stderr)
            return 1
        result = live_result
        fonte = "live"

    stats = result["stats"]
    n = stats["n"]
    print(
        f"  → fonte={fonte} n={n} mediana=R${stats['mediana']:,.2f} "
        f"P25=R${stats['p25']:,.2f} P75=R${stats['p75']:,.2f} CV={stats['cv']}%"
    )
    conf = confiability(n, stats.get("cv"))
    print(f"  Confiabilidade: {conf}")
    if conf == "AMOSTRA_HETEROGENEA":
        print(
            f"  ⚠ CV={stats['cv']}% > 200% — amostra mistura contratos "
            "não-comparáveis. Refine objeto com keywords mais específicas."
        )

    payload = {
        "objeto": args.objeto,
        "ufs": ufs or [],
        "meses": args.meses,
        "modalidades_usadas": modalidades if fonte == "live" else None,
        "fonte": fonte,
        "confiabilidade": conf,
        "stats": stats,
        "sample": result.get("sample", []),
        "keywords_used": result.get("keywords_used", keywords),
        "warnings": [
            "valor_global é cascade (homologado→inicial→estimado); ver caveat no .md",
        ],
        "meta": result.get("meta", {}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
