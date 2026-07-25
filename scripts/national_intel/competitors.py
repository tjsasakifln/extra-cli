"""Competitor / supplier geographic intelligence product."""

from __future__ import annotations

from typing import Any

from scripts.national_intel.db import fetch_all
from scripts.national_intel.lineage import envelope
from scripts.national_intel.sql_filters import build_contract_filters


def run_competitors(
    conn: Any,
    *,
    keyword: str | None = None,
    uf: str | None = None,
    limit: int = 50,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Rank suppliers by contract count with UF footprint.

    claim_class:
      - ufs, has_sc, contract_count, valor_sum → fact
      - ranking position → indicator
      - "potential entrant" flags → hypothesis (caller may annotate)
    """
    limit = max(1, min(int(limit), 5000))
    where, params = build_contract_filters(keyword=keyword, uf=uf)
    # WHERE built only from allowlisted fragments + %s binds (see sql_filters).
    sql = (
        "SELECT "
        "COALESCE(c.fornecedor_cnpj_8, left(COALESCE(c.fornecedor_cnpj, ''), 8)) "
        "AS fornecedor_cnpj_8, "
        "MAX(c.fornecedor_cnpj) AS fornecedor_cnpj, "
        "MAX(c.fornecedor_nome) AS fornecedor_nome, "
        "COUNT(*)::bigint AS contract_count, "
        "COUNT(DISTINCT upper(btrim(c.uf))) "
        "FILTER (WHERE c.uf IS NOT NULL AND btrim(c.uf) <> '')::bigint AS uf_count, "
        "array_agg(DISTINCT upper(btrim(c.uf)) ORDER BY upper(btrim(c.uf))) "
        "FILTER (WHERE c.uf IS NOT NULL AND btrim(c.uf) <> '') AS ufs, "
        "BOOL_OR(c.uf IS NOT NULL AND upper(btrim(c.uf)) = 'SC') AS has_sc, "
        "COALESCE(SUM(c.valor_total), 0)::numeric AS valor_sum "
        "FROM public.pncp_supplier_contracts c "
        "WHERE "
        + where
        + " AND ("
        " (c.fornecedor_cnpj IS NOT NULL AND btrim(c.fornecedor_cnpj) <> '') "
        " OR (c.fornecedor_nome IS NOT NULL AND btrim(c.fornecedor_nome) <> '') "
        ") "
        "GROUP BY 1 "
        "ORDER BY contract_count DESC, valor_sum DESC NULLS LAST "
        "LIMIT %s"
    )
    params.append(limit)
    raw = fetch_all(conn, sql, tuple(params))
    rows: list[dict[str, Any]] = []
    for i, r in enumerate(raw, start=1):
        ufs = r.get("ufs") or []
        if isinstance(ufs, str):
            ufs = [ufs]
        has_sc = bool(r.get("has_sc"))
        uf_count = int(r.get("uf_count") or 0)
        entry_hypothesis = None
        if not has_sc and uf_count >= 1 and keyword:
            entry_hypothesis = {
                "label": "potential_sc_entrant",
                "claim_class": "hypothesis",
                "reason": "Active outside SC on keyword filter; no SC contracts in filter window",
            }
        rows.append(
            {
                "rank": i,
                "rank_claim_class": "indicator",
                "fornecedor_cnpj_8": r.get("fornecedor_cnpj_8"),
                "fornecedor_cnpj": r.get("fornecedor_cnpj"),
                "fornecedor_nome": r.get("fornecedor_nome"),
                "contract_count": int(r.get("contract_count") or 0),
                "uf_count": uf_count,
                "ufs": list(ufs),
                "has_sc": has_sc,
                "valor_sum": float(r.get("valor_sum") or 0),
                "claim_class": "fact",
                "entrant_signal": entry_hypothesis,
            }
        )

    limitations = [
        "Keyword filter is lexical on objeto_contrato — not technical object equivalence.",
        "valor_sum is global contracted value (valor_total), not unit price or margin.",
        "Absence of SC contracts in this filter is not proof of non-operation in SC.",
        "No partnership/consortium is inferred from co-presence.",
        "National inventory completeness depends on upstream crawl windows — not assumed complete.",
    ]
    return envelope(
        product_id="competitors_geo",
        scope_label="intel_product",
        filters={"keyword": keyword, "uf": uf, "limit": limit},
        rows=rows,
        limitations=limitations,
        dsn=dsn,
    )
