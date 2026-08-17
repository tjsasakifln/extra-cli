#!/usr/bin/env python3
"""Campaign runner: official Market Answer at the smallest factual geography.

Uses shipped typology keywords, shipped percentile, and shipped projector.
Does not invent a second engine. Does not claim Brasil. Does not mark
keyword typology as sample_precision_reviewed.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.contract_comparables.metrics import _percentile
from scripts.contract_comparables.official_canary import PAVING_ILIKE
from scripts.public_read_consumers.export import export_consumer
from scripts.public_read_consumers.market_answer import CONSUMER_ID, project_market_answer

GEOGRAPHY_UF = "SC"
PERIOD_START = "2023-07-20"
ZERO_EXCLUDED_NOTE = "valor_total<=0 treated as missingness, never as a real ticket"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_values(dsn: str) -> tuple[tuple[Decimal, ...], list[str], str, str, int, int]:
    import psycopg2

    sql = """
    SELECT valor_total, contrato_id, data_publicacao::date, last_seen_at
    FROM pncp_supplier_contracts
    WHERE is_active IS TRUE
      AND uf = %s
      AND objeto_contrato IS NOT NULL
      AND (
           objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
        OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
      )
    ORDER BY contrato_id
    """
    connection = psycopg2.connect(dsn, connect_timeout=20)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, (GEOGRAPHY_UF, *PAVING_ILIKE))
            rows = cursor.fetchall()
    finally:
        connection.close()
    usable: list[Decimal] = []
    refs: list[str] = []
    dates: list[str] = []
    last_seen: list[str] = []
    missing = 0
    for valor, contrato_id, data_pub, seen in rows:
        if valor is None or Decimal(str(valor)) <= 0:
            missing += 1
            continue
        usable.append(Decimal(str(valor)))
        if len(refs) < 16:
            refs.append(str(contrato_id))
        dates.append(str(data_pub))
        if seen is not None:
            last_seen.append(seen.isoformat())
    ordered = tuple(sorted(usable))
    source_as_of = max(last_seen) if last_seen else _now()
    period_end = max(dates) if dates else PERIOD_START
    return ordered, refs, source_as_of, period_end, missing, len(rows)


def build_raw(ordered: tuple[Decimal, ...], refs: list[str], source_as_of: str, period_end: str, missing: int, total: int) -> dict[str, Any]:
    generated_at = _now()
    n = len(ordered)
    return {
        "generated_at": generated_at,
        "as_of": source_as_of,
        "source_as_of": source_as_of,
        "catalog_mode": "official_live",
        "claimed_live": True,
        "producer_status": "OFFICIAL_LIVE",
        "official_live": True,
        "grain": "integral_nominal_instrument",
        "question_id": "valor-tipico-contratos-pavimentacao",
        "typology_id": "pavimentacao/1.0",
        "typology": {
            "id": "pavimentacao/1.0",
            "method": "documented_keyword_classifier",
            "keywords": list(PAVING_ILIKE),
            # Intentionally omitted: sample_precision_reviewed is not a human review.
        },
        "stats": {
            "median": float(_percentile(ordered, 50)) if n else None,
            "p25": float(_percentile(ordered, 25)) if n else None,
            "p75": float(_percentile(ordered, 75)) if n else None,
            "n": n,
        },
        "period": {"start": PERIOD_START, "end": period_end},
        "geography": {"kind": "uf", "code": GEOGRAPHY_UF, "label": "Santa Catarina"},
        "currency": "BRL",
        "base": "nominal",
        "coverage": {
            "status": "COMPLETE" if n >= 8 else "INCOMPLETE",
            "n": n,
            "usable_n": n,
            "total_keyword_rows": total,
            "missing_or_nonpositive": missing,
        },
        "contract_refs": refs,
        "evidence_refs": [
            {
                "schema": "pncp_supplier_contracts",
                "database": "pncp_datalake",
                "table": "pncp_supplier_contracts",
                "filter": "uf=SC AND documented paving keywords AND valor_total>0",
            }
        ],
        "peer_group": {
            "status": "NOT_COMPARABLE",
            "ref": None,
            "issue": "#415",
            "reason_codes": ["live_columns_unavailable", "unit_unknown"],
        },
        "limitations": [
            "Ticket is the integral nominal instrument value, never cost per km.",
            "Geography is Santa Catarina, not Brasil. National claim is not authorized (#302 tables absent).",
            "Typology is the documented keyword classifier from official_canary, not an official regime column.",
            "sample_precision_reviewed was not performed; keyword matches can include mixed paving scopes.",
            ZERO_EXCLUDED_NOTE,
            "Comparables (#415) remain NOT_COMPARABLE: official table lacks unidade/quantidade/regime/modalidade/valor_semantic.",
        ],
        "missingness": {"unknown_or_nonpositive": missing, "usable": n, "total_keyword_rows": total},
        "suppression": {"applied": True, "reason_codes": ["nonpositive_valor_excluded"]},
        "claim": {
            "schema": "national_universe/1.0",
            "producer_status": "OFFICIAL_LIVE",
            "official_live": True,
            "authorization_state": "NEEDS_DATA",
            "nacional_completo": False,
            "national_claim_allowed": False,
            "reason_codes": ["national_claims_tables_absent"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.stderr.write("usage: produce_sc_market_answer.py OUT_DIR\n")
        return 2
    dsn = os.environ.get("LOCAL_DATALAKE_DSN")
    if not dsn:
        sys.stderr.write("LOCAL_DATALAKE_DSN absent\n")
        return 2
    ordered, refs, source_as_of, period_end, missing, total = fetch_values(dsn)
    raw = build_raw(ordered, refs, source_as_of, period_end, missing, total)
    projected = project_market_answer(raw)
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = export_consumer(CONSUMER_ID, raw, out / "export", fixture=False, live=True, now=raw["generated_at"])
    print(json.dumps({"ok": True, "projected_official_live": projected.get("official_live"), "answer_state": projected.get("answer_state"), "n": projected.get("stats", {}).get("n"), "geography": projected.get("geography"), "export": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
