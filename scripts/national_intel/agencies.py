"""Contracting agency profile product (single-query, no N+1)."""

from __future__ import annotations

from typing import Any

from scripts.national_intel.db import fetch_all
from scripts.national_intel.lineage import envelope
from scripts.national_intel.sql_filters import build_contract_filters


def run_agencies(
    conn: Any,
    *,
    keyword: str | None = None,
    uf: str | None = None,
    limit: int = 50,
    dsn: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 5000))
    where, params = build_contract_filters(keyword=keyword, uf=uf)
    # where is allowlisted-only (sql_filters); params bind all user values.
    head = (
        "WITH base AS ("
        "  SELECT "
        "    COALESCE(c.orgao_cnpj_8, left(COALESCE(c.orgao_cnpj, ''), 8)) AS orgao_cnpj_8, "
        "    c.orgao_cnpj, c.orgao_nome, "
        "    COALESCE(c.fornecedor_cnpj_8, c.fornecedor_cnpj) AS supplier_key, "
        "    c.valor_total, c.uf, c.data_publicacao "
        "  FROM public.pncp_supplier_contracts c "
        "  WHERE "
    )
    tail = (
        "    AND ("
        "      (c.orgao_cnpj IS NOT NULL AND btrim(c.orgao_cnpj) <> '') "
        "      OR (c.orgao_nome IS NOT NULL AND btrim(c.orgao_nome) <> '') "
        "    )"
        "), "
        "supplier_counts AS ("
        "  SELECT orgao_cnpj_8, supplier_key, COUNT(*)::numeric AS n "
        "  FROM base GROUP BY orgao_cnpj_8, supplier_key"
        "), "
        "supplier_totals AS ("
        "  SELECT orgao_cnpj_8, SUM(n) AS total_n "
        "  FROM supplier_counts GROUP BY orgao_cnpj_8"
        "), "
        "top_share AS ("
        "  SELECT sc.orgao_cnpj_8, "
        "    MAX(sc.n / NULLIF(st.total_n, 0)) AS top_supplier_share "
        "  FROM supplier_counts sc "
        "  JOIN supplier_totals st ON st.orgao_cnpj_8 = sc.orgao_cnpj_8 "
        "  GROUP BY sc.orgao_cnpj_8"
        "), "
        "ranked AS ("
        "  SELECT "
        "    b.orgao_cnpj_8, "
        "    MAX(b.orgao_cnpj) AS orgao_cnpj, "
        "    MAX(b.orgao_nome) AS orgao_nome, "
        "    COUNT(*)::bigint AS contract_count, "
        "    COUNT(DISTINCT b.supplier_key)::bigint AS supplier_count, "
        "    COALESCE(SUM(b.valor_total), 0)::numeric AS valor_sum, "
        "    AVG(b.valor_total)::numeric AS valor_avg, "
        "    percentile_cont(0.5) WITHIN GROUP (ORDER BY b.valor_total) "
        "      FILTER (WHERE b.valor_total IS NOT NULL) AS valor_p50, "
        "    MODE() WITHIN GROUP (ORDER BY upper(btrim(b.uf))) "
        "      FILTER (WHERE b.uf IS NOT NULL AND btrim(b.uf) <> '') AS uf_mode, "
        "    MIN(b.data_publicacao) AS first_publicacao, "
        "    MAX(b.data_publicacao) AS last_publicacao "
        "  FROM base b "
        "  GROUP BY b.orgao_cnpj_8"
        ") "
        "SELECT r.*, COALESCE(t.top_supplier_share, 0) AS top_supplier_share "
        "FROM ranked r "
        "LEFT JOIN top_share t ON t.orgao_cnpj_8 = r.orgao_cnpj_8 "
        "ORDER BY r.contract_count DESC, r.valor_sum DESC NULLS LAST "
        "LIMIT %s"
    )
    sql = head + where + tail  # noqa: S608
    params.append(limit)
    raw = fetch_all(conn, sql, tuple(params))

    rows: list[dict[str, Any]] = []
    for r in raw:
        rows.append(
            {
                "orgao_cnpj_8": r.get("orgao_cnpj_8"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "orgao_nome": r.get("orgao_nome"),
                "contract_count": int(r.get("contract_count") or 0),
                "supplier_count": int(r.get("supplier_count") or 0),
                "valor_sum": float(r.get("valor_sum") or 0),
                "valor_avg": float(r["valor_avg"]) if r.get("valor_avg") is not None else None,
                "valor_p50": float(r["valor_p50"]) if r.get("valor_p50") is not None else None,
                "uf_mode": r.get("uf_mode"),
                "first_publicacao": r.get("first_publicacao"),
                "last_publicacao": r.get("last_publicacao"),
                "top_supplier_share": float(r.get("top_supplier_share") or 0),
                "top_supplier_share_claim_class": "indicator",
                "claim_class": "fact",
            }
        )

    limitations = [
        "Agency profiles reflect inventory present in pncp_supplier_contracts for the filter only.",
        "top_supplier_share is an INDICATOR of concentration, not proof of collusion or exclusive partnership.",
        "uf_mode is MODE of contracts, not legal jurisdiction of the agency.",
        "Empty result means no matching rows in filter — not a claim of zero public demand nationally.",
    ]
    return envelope(
        product_id="agencies_profile",
        scope_label="intel_product",
        filters={"keyword": keyword, "uf": uf, "limit": limit},
        rows=rows,
        limitations=limitations,
        dsn=dsn,
    )
