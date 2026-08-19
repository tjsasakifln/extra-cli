"""CLI: python3 -m scripts.traffic_frontier --out DIR [--as-of DATE]"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.traffic_frontier.catalog import CATALOG_AS_OF
from scripts.traffic_frontier.export import build_frontier_pack, write_frontier_pack

BOUNDED_PROBE_SQL = """
SELECT
  current_setting('transaction_read_only') AS txn_read_only
WHERE false
LIMIT 1
"""


def _probe_dsn(dsn: str) -> dict[str, Any]:
    """Bounded SELECT-only probe. Never writes. Absence is recorded, not invented."""
    try:
        import psycopg
    except ImportError:
        return {"ok": False, "reason": "psycopg_missing", "dsn_present": True}
    try:
        with psycopg.connect(dsn, connect_timeout=2, autocommit=True) as conn:
            conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            conn.execute("SET statement_timeout = 2000")
            with conn.cursor() as cur:
                cur.execute(BOUNDED_PROBE_SQL)
                _ = cur.fetchall()
        return {"ok": True, "reason": "select_ok", "row_count": 0, "as_of": CATALOG_AS_OF}
    except Exception as exc:  # noqa: BLE001 — probe must never raise to CLI
        return {"ok": False, "reason": type(exc).__name__, "detail": str(exc)[:240]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the factual traffic-opportunity frontier pack (producer-only).")
    parser.add_argument("--out", required=True, help="Output directory for the versioned pack")
    parser.add_argument(
        "--as-of",
        default=CATALOG_AS_OF,
        help="Frozen snapshot date (default: catalog as_of, never wall-clock)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("LOCAL_DATALAKE_DSN"),
        help="Optional DSN for a bounded SELECT-only probe",
    )
    parser.add_argument(
        "--probe-out",
        default=None,
        help="Optional JSON path to write the DSN probe result",
    )
    args = parser.parse_args(argv)

    source_access = "fixtures"
    probe: dict[str, Any] | None = None
    if args.dsn:
        probe = _probe_dsn(args.dsn)
        source_access = "dsn_ok" if probe.get("ok") else "dsn_unavailable"
    else:
        probe = {"ok": False, "reason": "dsn_absent"}
        source_access = "fixtures"

    pack = build_frontier_pack(as_of=args.as_of, source_access=source_access)
    dest = write_frontier_pack(pack, args.out)
    if args.probe_out:
        Path(args.probe_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.probe_out).write_text(
            json.dumps(probe, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "out": str(dest),
                "schema": pack["schema"],
                "as_of": pack["as_of"],
                "campaign_status": pack["campaign_status"],
                "top3": [item["opportunity_id"] for item in pack["top3"]],
                "counts": pack["manifest"]["counts"],
                "no_publication_authorization": True,
                "no_index_authorization": True,
                "source_access": source_access,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    return 0
