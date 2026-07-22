"""Contracting agency profile product."""

from __future__ import annotations

from typing import Any

from scripts.national_intel.db import fetch_all
from scripts.national_intel.lineage import envelope


def run_agencies(
    conn: Any,
    *,
    keyword: str | None = None,
    uf: str | None = None,
    limit: int = 50,
    dsn: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 5000))
    clauses = ["c.is_active = TRUE"]
    params: list[Any] = []
    if keyword:
        clauses.append("c.objeto_contrato ILIKE %s")
        params.append(f"%{keyword}%")
    if uf:
        clauses.append("upper(btrim(c.uf)) = upper(btrim(%s))")
        params.append(uf)
    where = " AND ".join(clauses)
    sql = f"""
    WITH base AS (
        SELECT
            COALESCE(c.orgao_cnpj_8, left(COALESCE(c.orgao_cnpj, ''), 8)) AS orgao_cnpj_8,
            c.orgao_cnpj,
            c.orgao_nome,
            c.fornecedor_cnpj_8,
            c.fornecedor_cnpj,
            c.valor_total,
            c.uf,
            c.data_publicacao
        FROM public.pncp_supplier_contracts c
        WHERE {where}
          AND (
                (c.orgao_cnpj IS NOT NULL AND btrim(c.orgao_cnpj) <> '')
                OR (c.orgao_nome IS NOT NULL AND btrim(c.orgao_nome) <> '')
              )
    ),
    ranked AS (
        SELECT
            orgao_cnpj_8,
            MAX(orgao_cnpj) AS orgao_cnpj,
            MAX(orgao_nome) AS orgao_nome,
            COUNT(*)::bigint AS contract_count,
            COUNT(DISTINCT COALESCE(fornecedor_cnpj_8, fornecedor_cnpj))::bigint AS supplier_count,
            COALESCE(SUM(valor_total), 0)::numeric AS valor_sum,
            AVG(valor_total)::numeric AS valor_avg,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY valor_total)
                FILTER (WHERE valor_total IS NOT NULL) AS valor_p50,
            MODE() WITHIN GROUP (ORDER BY upper(btrim(uf)))
                FILTER (WHERE uf IS NOT NULL AND btrim(uf) <> '') AS uf_mode,
            MIN(data_publicacao) AS first_publicacao,
            MAX(data_publicacao) AS last_publicacao
        FROM base
        GROUP BY orgao_cnpj_8
    )
    SELECT * FROM ranked
    ORDER BY contract_count DESC, valor_sum DESC NULLS LAST
    LIMIT %s
    """
    params.append(limit)
    raw = fetch_all(conn, sql, tuple(params))

    # top supplier share (concentration indicator) per agency — second query batched lightly
    rows: list[dict[str, Any]] = []
    for r in raw:
        oid = r.get("orgao_cnpj_8")
        share_sql = """
        SELECT COALESCE(MAX(share), 0) AS top_supplier_share
        FROM (
            SELECT COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (), 0) AS share
            FROM public.pncp_supplier_contracts c
            WHERE c.is_active = TRUE
              AND COALESCE(c.orgao_cnpj_8, left(COALESCE(c.orgao_cnpj, ''), 8)) = %s
            GROUP BY COALESCE(c.fornecedor_cnpj_8, c.fornecedor_cnpj)
        ) s
        """
        share_rows = fetch_all(conn, share_sql, (oid,))
        top_share = float(share_rows[0]["top_supplier_share"]) if share_rows else 0.0
        rows.append(
            {
                "orgao_cnpj_8": oid,
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
                "top_supplier_share": top_share,
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
