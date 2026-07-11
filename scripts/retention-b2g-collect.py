#!/usr/bin/env python3
"""retention-b2g coletor — DataLake-first p/ pacote retencao + upsell.

Substitui 3 APIs paralelas (OpenCNPJ + PNCP + Portal Transparencia) por:
  - DatalakeClient.enriched_entity('fornecedor', cnpj14)  # cache OpenCNPJ + sancoes
  - DatalakeClient.supplier_contracts(ni_fornecedor=cnpj14, meses=3)  # contratos recentes
  - DatalakeClient.supplier_contracts(ni_fornecedor=cnpj14, meses=12) # baseline
  - DatalakeClient.search_bids(ufs, tsquery=setor_kws, dias=30, modo='abertas') # oportunidades
  - DatalakeClient.top_competitors(orgao_cnpj=cliente_orgao_top, meses=24)       # sinal churn

Live fallbacks (sob demanda):
  - OpenCNPJ live se enriched_entity cache miss
  - Portal Transparencia (PT_KEY) — sancoes; cacheavel em enriched_entities.data.sancoes
    (sub-TTL 7d) — neste pilot apenas placeholder se PT_KEY ausente

CLI:
    python scripts/retention-b2g-collect.py --cnpj 12345678000190 --output ...
    python scripts/retention-b2g-collect.py --cnpj all --carteira docs/carteira-clientes.json --output ...

Output JSON (per-CNPJ ou {clientes: [...]} se 'all'):
    {
      "cnpj":"...","perfil":{razao_social,cnae_principal,ufs_atuacao,...},
      "performance":{contratos_3m, valor_3m, novos_orgaos, novas_ufs,
                     delta_vs_trimestre_anterior},
      "oportunidades":[{...top 30 editais setor abertos...}],
      "sancoes":[...],
      "fonte":"datalake","generated_at":"..."
    }

Health score, upsell signals, churn flags: calculados por Claude consumindo JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from datalake_helper import DatalakeClient  # noqa: E402


_DEFAULT_OPPORTUNITY_LIMIT = 30
_OPENCNPJ_URL = "https://api.opencnpj.org/{cnpj}"


# ---------------------------------------------------------------------------
# Sectors helper (reuso minimo do radar pattern)
# ---------------------------------------------------------------------------

def load_sectors() -> dict:
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


def keywords_from_setor(setor: str, sectors: dict) -> list[str]:
    if setor and setor in sectors:
        return [k.lower() for k in sectors[setor].get("keywords", [])]
    return []


def _tsquery_or(keywords: list[str]) -> str | None:
    """OR-tsquery; palavras compostas viram (a & b)."""
    if not keywords:
        return None
    parts = []
    for k in keywords:
        toks = [t for t in "".join(c if c.isalnum() or c == "-" else " " for c in k).split() if t]
        if not toks:
            continue
        parts.append(toks[0] if len(toks) == 1 else "(" + " & ".join(toks) + ")")
    return " | ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# OpenCNPJ live fetch (cache miss)
# ---------------------------------------------------------------------------

def _opencnpj_live(cnpj14: str) -> dict | None:
    try:
        import httpx
    except ImportError:
        return None
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(_OPENCNPJ_URL.format(cnpj=cnpj14))
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


def _normalize_perfil(opencnpj_data: dict | None) -> dict:
    if not opencnpj_data:
        return {}
    cnaes = opencnpj_data.get("cnaes_secundarios") or []
    cnae_principal = opencnpj_data.get("cnae_principal") or {}
    ufs = set()
    if opencnpj_data.get("uf"):
        ufs.add(opencnpj_data["uf"])
    return {
        "razao_social": opencnpj_data.get("razao_social"),
        "nome_fantasia": opencnpj_data.get("nome_fantasia"),
        "cnae_principal": cnae_principal.get("codigo") if isinstance(cnae_principal, dict) else cnae_principal,
        "cnae_principal_descricao": cnae_principal.get("descricao") if isinstance(cnae_principal, dict) else None,
        "cnaes_secundarios": [c.get("codigo") if isinstance(c, dict) else c for c in cnaes][:10],
        "porte": opencnpj_data.get("porte"),
        "capital_social": opencnpj_data.get("capital_social"),
        "ufs_atuacao": sorted(ufs),
        "situacao": opencnpj_data.get("situacao") or opencnpj_data.get("descricao_situacao_cadastral"),
    }


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def compute_performance(
    contratos_3m: list[dict],
    contratos_baseline_12m: list[dict],
) -> dict:
    """Agrega contratos em metricas comparaveis."""
    n3 = len(contratos_3m)
    v3 = sum(float(c.get("valor_global") or 0) for c in contratos_3m)
    orgaos_3m = {c.get("orgao_cnpj") for c in contratos_3m if c.get("orgao_cnpj")}
    ufs_3m = {c.get("uf") for c in contratos_3m if c.get("uf")}

    # Trimestre anterior = janela 3-6m do baseline 12m
    today = date.today()

    def in_quarter(c: dict, lower_days_ago: int, upper_days_ago: int) -> bool:
        d = c.get("data_assinatura")
        if not d:
            return False
        try:
            cd = datetime.fromisoformat(d.replace("Z", "+00:00")).date()
            delta_days = (today - cd).days
            return lower_days_ago <= delta_days < upper_days_ago
        except (ValueError, TypeError):
            return False

    contratos_q_anterior = [c for c in contratos_baseline_12m if in_quarter(c, 91, 182)]
    n_qa = len(contratos_q_anterior)
    v_qa = sum(float(c.get("valor_global") or 0) for c in contratos_q_anterior)

    def pct(novo: float, baseline: float) -> str:
        if baseline <= 0:
            return "+inf%" if novo > 0 else "0%"
        delta = (novo - baseline) / baseline * 100
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.0f}%"

    orgaos_baseline = {c.get("orgao_cnpj") for c in contratos_baseline_12m if c.get("orgao_cnpj")}
    novos_orgaos_3m = orgaos_3m - (orgaos_baseline - orgaos_3m)
    ufs_baseline = {c.get("uf") for c in contratos_baseline_12m if c.get("uf")}
    novas_ufs_3m = ufs_3m - (ufs_baseline - ufs_3m)

    return {
        "contratos_3m": n3,
        "valor_3m": round(v3, 2),
        "orgaos_unicos_3m": len(orgaos_3m),
        "ufs_atuacao_3m": sorted(ufs_3m),
        "novos_orgaos_3m": len(novos_orgaos_3m),
        "novas_ufs_3m": sorted(novas_ufs_3m),
        "contratos_q_anterior": n_qa,
        "valor_q_anterior": round(v_qa, 2),
        "delta_vs_trimestre_anterior": {
            "contratos": pct(n3, n_qa),
            "valor": pct(v3, v_qa),
        },
        "contratos_12m_total": len(contratos_baseline_12m),
        "valor_12m_total": round(sum(float(c.get("valor_global") or 0) for c in contratos_baseline_12m), 2),
    }


# ---------------------------------------------------------------------------
# Per-CNPJ collection
# ---------------------------------------------------------------------------

def collect_for_cnpj(
    cnpj14: str,
    meses: int,
    setor: str,
    setor_kws: list[str],
    ufs_filtro: list[str] | None,
    dl: DatalakeClient,
    use_dl: bool,
) -> dict:
    """Coleta full pipeline retention p/ 1 cliente."""
    fonte = "datalake" if use_dl and dl.is_enabled else "live_only"
    warnings: list[str] = []

    perfil_data: dict | None = None
    perfil_meta: dict = {}
    if use_dl and dl.is_enabled:
        perfil_data, perfil_meta = dl.enriched_entity("fornecedor", cnpj14)

    if perfil_data is None:
        opencnpj = _opencnpj_live(cnpj14)
        perfil_data = opencnpj
        perfil_meta = {"source": "opencnpj_live"}
        if opencnpj is None:
            warnings.append("OpenCNPJ live failed — perfil parcial")

    perfil = _normalize_perfil(perfil_data) if isinstance(perfil_data, dict) else {}

    # Inferir UFs de filtro: do perfil ou fornecidas
    ufs = ufs_filtro or perfil.get("ufs_atuacao") or []

    # Contratos recentes + baseline
    contratos_3m: list[dict] = []
    contratos_12m: list[dict] = []
    contratos_meta: dict = {}
    if use_dl and dl.is_enabled:
        c3, m3 = dl.supplier_contracts(ni_fornecedor=cnpj14, meses=3, limit=1000)
        c12, m12 = dl.supplier_contracts(ni_fornecedor=cnpj14, meses=12, limit=1000)
        contratos_3m = c3 or []
        contratos_12m = c12 or []
        contratos_meta = {"3m": m3, "12m": m12}
        if c3 is None or c12 is None:
            warnings.append("DataLake supplier_contracts retornou None — possivel ETL stale")

    performance = compute_performance(contratos_3m, contratos_12m)

    # Oportunidades abertas no setor
    oportunidades: list[dict] = []
    op_meta: dict = {}
    if use_dl and dl.is_enabled:
        tsq = _tsquery_or(setor_kws)
        if tsq:
            ops, op_meta = dl.search_bids(
                ufs=ufs or None,
                dias=30,
                tsquery=tsq,
                modalidades=[4, 5, 6, 8],
                modo="abertas",
                paginate_by_uf_modalidade=bool(ufs),
                limit=2000,
            )
            if ops:
                # Top N por valor + prazo (dias até encerramento crescente)
                today = date.today()

                def ranking(b: dict) -> tuple:
                    valor = float(b.get("valor_total_estimado") or 0)
                    enc = b.get("data_encerramento")
                    dias_ate = 999
                    if enc:
                        try:
                            d = datetime.fromisoformat(enc.replace("Z", "+00:00")).date()
                            dias_ate = max(0, (d - today).days)
                        except (ValueError, TypeError):
                            pass
                    return (-valor, dias_ate)

                ranked = sorted(ops, key=ranking)[:_DEFAULT_OPPORTUNITY_LIMIT]
                oportunidades = [{
                    "pncp_id": b.get("pncp_id"),
                    "objeto_compra": b.get("objeto_compra"),
                    "valor_total_estimado": float(b.get("valor_total_estimado") or 0),
                    "uf": b.get("uf"),
                    "municipio": b.get("municipio"),
                    "orgao_cnpj": b.get("orgao_cnpj"),
                    "orgao_razao_social": b.get("orgao_razao_social"),
                    "modalidade_nome": b.get("modalidade_nome"),
                    "data_encerramento": b.get("data_encerramento"),
                    "link_pncp": b.get("link_pncp"),
                } for b in ranked]

    # Concorrência: top competitors do orgão TOP do cliente (sinal churn)
    competitors_top_orgao: list[dict] = []
    if use_dl and dl.is_enabled and contratos_12m:
        # Encontra orgao_cnpj com mais contratos do cliente
        orgao_count: dict[str, int] = {}
        for c in contratos_12m:
            on = c.get("orgao_cnpj")
            if on:
                orgao_count[on] = orgao_count.get(on, 0) + 1
        if orgao_count:
            top_orgao = max(orgao_count, key=lambda k: orgao_count[k])
            comps, _ = dl.top_competitors(orgao_cnpj=top_orgao, meses=24, limit=10)
            if comps:
                competitors_top_orgao = [c for c in comps if c["ni_fornecedor"] != cnpj14][:5]

    # Sancoes — placeholder (Portal Transparencia requer PT_KEY ausente em prod-dev)
    sancoes: list[dict] = []
    if isinstance(perfil_data, dict) and perfil_data.get("sancoes"):
        sancoes = perfil_data["sancoes"]
    else:
        warnings.append("Sancoes nao consultadas (Portal Transparencia placeholder)")

    return {
        "cnpj": cnpj14,
        "perfil": perfil,
        "perfil_meta": perfil_meta,
        "performance": performance,
        "oportunidades": oportunidades,
        "oportunidades_meta": op_meta,
        "competitors_top_orgao": competitors_top_orgao,
        "sancoes": sancoes,
        "setor": setor,
        "setor_keywords_used": setor_kws,
        "warnings": warnings,
        "contratos_meta": contratos_meta,
        "fonte": fonte,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Carteira loading
# ---------------------------------------------------------------------------

def load_carteira(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERRO: carteira nao encontrada: {path}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("clientes") or []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Retention B2G — DataLake-first")
    ap.add_argument("--cnpj", required=True, help="CNPJ unico ou 'all'")
    ap.add_argument("--carteira", help="JSON carteira (necessario se --cnpj all)")
    ap.add_argument("--setor", default="", help="Setor (resolve keywords); fallback: usa CNAE/perfil")
    ap.add_argument("--uf", default="", help="UFs CSV opcional (override do perfil)")
    ap.add_argument("--meses", type=int, default=3, help="Janela contratos recentes (default 3)")
    ap.add_argument("--health", action="store_true", help="Inclui dashboard saude da carteira (only --cnpj all)")
    ap.add_argument("--upsell", action="store_true", help="Foco em sinais de upsell")
    ap.add_argument("--churn-risk", action="store_true", help="Foco em sinais de churn")
    ap.add_argument("--no-datalake", action="store_true", help="Forca live (sem DataLake)")
    ap.add_argument("--output", required=True, help="JSON de saida")
    args = ap.parse_args()

    sectors = load_sectors()
    dl = DatalakeClient()
    use_dl = (not args.no_datalake) and os.getenv("DATALAKE_QUERY_ENABLED", "").lower() in ("true", "1") and dl.is_enabled
    if not use_dl:
        print("AVISO: DataLake desabilitado — collect parcial (perfil live + sem contratos historicos).", file=sys.stderr)

    ufs_filtro = [u.strip().upper() for u in (args.uf or "").split(",") if u.strip()]

    if args.cnpj.lower() == "all":
        if not args.carteira:
            print("ERRO: --cnpj all requer --carteira", file=sys.stderr)
            return 2
        clientes = load_carteira(Path(args.carteira))
        out_clientes: list[dict] = []
        for c in clientes:
            cnpj14 = "".join(ch for ch in (c.get("cnpj") or "") if ch.isdigit())
            if not cnpj14:
                continue
            setor = c.get("setor") or args.setor
            kws = list(set(keywords_from_setor(setor, sectors) + (c.get("keywords_extras") or [])))
            ufs_c = ufs_filtro or [u.upper() for u in (c.get("ufs_interesse") or [])]
            print(f"[retention] {cnpj14} | {c.get('nome_fantasia','?')[:30]} | setor={setor} | kws={len(kws)} | ufs={ufs_c}")
            t = time.time()
            res = collect_for_cnpj(cnpj14, args.meses, setor, kws, ufs_c, dl, use_dl)
            res["nome_fantasia_carteira"] = c.get("nome_fantasia")
            res["pacote"] = c.get("pacote")
            print(f"  {time.time()-t:.1f}s | contratos_3m={res['performance']['contratos_3m']} "
                  f"oportunidades={len(res['oportunidades'])} warnings={len(res['warnings'])}")
            out_clientes.append(res)

        payload = {
            "modo": "all",
            "n_clientes": len(out_clientes),
            "clientes": out_clientes,
            "fonte": "datalake" if use_dl else "live_only",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "flags": {"health": args.health, "upsell": args.upsell, "churn_risk": args.churn_risk},
        }
    else:
        cnpj14 = "".join(ch for ch in args.cnpj if ch.isdigit())
        if len(cnpj14) != 14:
            print(f"ERRO: CNPJ invalido: {args.cnpj}", file=sys.stderr)
            return 2
        setor = args.setor
        kws = keywords_from_setor(setor, sectors)
        print(f"[retention] {cnpj14} setor={setor!r} kws={len(kws)} ufs={ufs_filtro}")
        t = time.time()
        payload = collect_for_cnpj(cnpj14, args.meses, setor, kws, ufs_filtro, dl, use_dl)
        payload["flags"] = {"health": args.health, "upsell": args.upsell, "churn_risk": args.churn_risk}
        print(f"  {time.time()-t:.1f}s | contratos_3m={payload['performance']['contratos_3m']} "
              f"oportunidades={len(payload['oportunidades'])} warnings={len(payload['warnings'])}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
