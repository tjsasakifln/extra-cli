#!/usr/bin/env python3
"""CLI to wire DedupEngine into the operational pipeline (C2.8 / NEXT-30D).

Runs cross-source deduplication on active opportunity_intel rows and persists
groups into dedup_cross_source. Produces a before/after JSON report.

Usage:
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --dry-run
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --dsn postgresql://...
    PYTHONPATH=. python3 scripts/crawl/run_dedup.py --output output/dedup/run.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _resolve_dsn(explicit: str | None) -> str:
    if explicit:
        return explicit
    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if dsn:
        return dsn
    try:
        from config.settings import LOCAL_DATALAKE_DSN

        return LOCAL_DATALAKE_DSN
    except ImportError:
        return "postgresql://test:test@127.0.0.1:5433/pncp_datalake"


def _count_dedup(conn: Any) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM dedup_cross_source")
    total = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(DISTINCT dedup_group_id) FROM dedup_cross_source
        """
    )
    groups = cur.fetchone()[0]
    cur.execute(
        """
        SELECT count(*) FROM opportunity_intel WHERE is_active IS TRUE
        """
    )
    active_ops = cur.fetchone()[0]
    cur.execute(
        """
        SELECT source, count(*) FROM opportunity_intel
        WHERE is_active IS TRUE
        GROUP BY source ORDER BY 2 DESC
        """
    )
    by_source = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return {
        "dedup_rows": total,
        "dedup_groups": groups,
        "active_opportunities": active_ops,
        "opportunities_by_source": by_source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cross-source DedupEngine")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute groups without writing dedup_cross_source",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON report path (default: output/dedup/dedup-<ts>.json)",
    )
    args = parser.parse_args()

    dsn = _resolve_dsn(args.dsn)
    import psycopg2

    from scripts.lib.dedup import DedupEngine

    run_id = f"dedup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    report: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": bool(args.dry_run),
        "dsn_host": dsn.split("@")[-1] if "@" in dsn else "local",
    }

    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        before = _count_dedup(conn)
        report["before"] = before
        engine = DedupEngine(conn)
        stats = engine.dedup_opportunities(dry_run=bool(args.dry_run))
        report["engine_stats"] = stats
        if not args.dry_run:
            after = _count_dedup(conn)
        else:
            after = before
        report["after"] = after
        report["delta_dedup_rows"] = after["dedup_rows"] - before["dedup_rows"]
        report["delta_dedup_groups"] = after["dedup_groups"] - before["dedup_groups"]

        # Honest classification
        if before["active_opportunities"] == 0:
            report["outcome"] = "success_zero"
            report["note"] = "No active opportunities; nothing to dedup"
            exit_code = 0
        elif stats.get("groups_found", 0) == 0:
            multi = len(before.get("opportunities_by_source") or {}) >= 2
            if multi:
                report["outcome"] = "success_zero"
                report["note"] = (
                    "Multi-source data present but no cross-source hash groups; "
                    "not a failure — may indicate no true duplicates"
                )
                exit_code = 0
            else:
                report["outcome"] = "partial"
                report["note"] = (
                    "Only single-source opportunities; cannot prove cross-source dedup"
                )
                exit_code = 0
        else:
            report["outcome"] = "success"
            report["note"] = "Cross-source groups written or detected"
            exit_code = 0

        out = (
            Path(args.output)
            if args.output
            else _PROJECT_ROOT / "output" / "dedup" / f"{run_id}.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        report["report_path"] = str(out)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return exit_code
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
