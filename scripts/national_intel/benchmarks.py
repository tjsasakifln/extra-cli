"""Value benchmark product with sample-size gate."""

from __future__ import annotations

from typing import Any

from scripts.national_intel.db import fetch_all
from scripts.national_intel.lineage import envelope


DEFAULT_MIN_SAMPLE = 20


def run_benchmarks(
    conn: Any,
    *,
    keyword: str | None = None,
    uf: str | None = None,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    dsn: str | None = None,
) -> dict[str, Any]:
    min_sample = max(1, int(min_sample))
    clauses = ["c.is_active = TRUE", "c.valor_total IS NOT NULL"]
    params: list[Any] = []
    if keyword:
        clauses.append("c.objeto_contrato ILIKE %s")
        params.append(f"%{keyword}%")
    if uf:
        clauses.append("upper(btrim(c.uf)) = upper(btrim(%s))")
        params.append(uf)
    where = " AND ".join(clauses)
    sql = f"""
    SELECT
        COUNT(*)::bigint AS n,
        MIN(c.valor_total)::numeric AS valor_min,
        MAX(c.valor_total)::numeric AS valor_max,
        AVG(c.valor_total)::numeric AS valor_avg,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY c.valor_total) AS valor_p50,
        percentile_cont(0.9) WITHIN GROUP (ORDER BY c.valor_total) AS valor_p90
    FROM public.pncp_supplier_contracts c
    WHERE {where}
    """
    stats = fetch_all(conn, sql, tuple(params))
    s = stats[0] if stats else {}
    n = int(s.get("n") or 0)
    status = "ok" if n >= min_sample else "insufficient_sample"
    rows: list[dict[str, Any]] = []
    if status == "ok":
        rows.append(
            {
                "status": status,
                "sample_size": n,
                "valor_min": float(s["valor_min"]) if s.get("valor_min") is not None else None,
                "valor_max": float(s["valor_max"]) if s.get("valor_max") is not None else None,
                "valor_avg": float(s["valor_avg"]) if s.get("valor_avg") is not None else None,
                "valor_p50": float(s["valor_p50"]) if s.get("valor_p50") is not None else None,
                "valor_p90": float(s["valor_p90"]) if s.get("valor_p90") is not None else None,
                "unit_price": None,
                "unit_price_claim_class": "not_applicable",
                "claim_class": "indicator",
            }
        )
    else:
        rows.append(
            {
                "status": status,
                "sample_size": n,
                "min_sample_required": min_sample,
                "claim_class": "indicator",
            }
        )

    limitations = [
        f"Minimum sample size for percentiles: {min_sample}.",
        "Objects matched by keyword are not guaranteed technically comparable.",
        "valor_total is global contract value — unit price omitted without valid quantity denominator.",
        "Do not treat benchmark as Extra bid price recommendation without human review.",
        "Filter may mix different modalities and scopes of work.",
    ]
    return envelope(
        product_id="benchmarks_value",
        scope_label="intel_product",
        filters={"keyword": keyword, "uf": uf, "min_sample": min_sample},
        rows=rows,
        limitations=limitations,
        dsn=dsn,
        extra={"status": status, "sample_size": n},
    )
