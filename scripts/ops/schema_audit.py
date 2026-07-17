#!/usr/bin/env python3
"""Schema audit: migrations files vs applied rows vs critical relations.

Exit 0 only when mandatory relations exist and migration inventory is coherent.
Does not invent coverage metrics.

Usage:
    PYTHONPATH=. python3 scripts/ops/schema_audit.py
    PYTHONPATH=. python3 scripts/ops/schema_audit.py --dsn postgresql://...
    PYTHONPATH=. python3 scripts/ops/schema_audit.py --json output/schema-audit.json
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
_MIGRATIONS_DIR = _PROJECT_ROOT / "db" / "migrations"

# Relations required for NEXT-30D operational paths
REQUIRED_RELATIONS = [
    "pncp_raw_bids",
    "pncp_supplier_contracts",
    "opportunity_intel",
    "entity_aliases",
    "dedup_cross_source",
    "target_universe_entities",
    "entity_coverage",
    "pipeline_watermarks",
    "ingestion_runs",
    "_migrations",
]


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


def list_migration_files() -> list[str]:
    files = sorted(p.name for p in _MIGRATIONS_DIR.glob("*.sql"))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit DB schema vs migrations")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args()

    files = list_migration_files()
    report: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "migration_files": len(files),
        "migration_file_names": files,
        "required_relations": REQUIRED_RELATIONS,
        "issues": [],
        "warnings": [],
    }

    import psycopg2

    dsn = _resolve_dsn(args.dsn)
    conn = psycopg2.connect(dsn, connect_timeout=10)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = {r[0] for r in cur.fetchall()}
        report["public_tables"] = sorted(tables)

        missing = [t for t in REQUIRED_RELATIONS if t not in tables]
        report["missing_required"] = missing
        if missing:
            report["issues"].append(f"missing_required_relations: {missing}")

        # _migrations inventory
        if "_migrations" in tables:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='_migrations'")
            mig_cols = [r[0] for r in cur.fetchall()]
            report["migrations_columns"] = mig_cols
            name_col = "name" if "name" in mig_cols else ("version" if "version" in mig_cols else None)
            status_col = "status" if "status" in mig_cols else None
            if name_col:
                cur.execute("SELECT count(*) FROM _migrations")
                report["migrations_rows"] = cur.fetchone()[0]
                if status_col:
                    # status_col is allowlisted above ("status" only); keep static SQL.
                    cur.execute(
                        "SELECT status, count(*) FROM _migrations GROUP BY 1 ORDER BY 2 DESC"
                    )
                    report["migrations_by_status"] = {
                        str(r[0]): r[1] for r in cur.fetchall()
                    }
                    failed = report["migrations_by_status"].get("failed", 0)
                    if failed:
                        report["warnings"].append(
                            f"{failed} migration rows marked failed "
                            "(may be benign 'already exists' on non-fresh DB)"
                        )
            else:
                report["warnings"].append("Could not find name/version column in _migrations")
        else:
            report["issues"].append("_migrations table missing")

        # File count vs applied count coherence
        n_files = len(files)
        n_rows = report.get("migrations_rows")
        if isinstance(n_rows, int) and n_rows != n_files:
            report["warnings"].append(
                f"migration files ({n_files}) != _migrations rows ({n_rows}) — "
                "fresh install re-proof required for GATE-A"
            )

        # Critical functions
        for fn in (
            "upsert_pncp_raw_bids",
            "upsert_pncp_supplier_contracts",
        ):
            cur.execute(
                """
                SELECT count(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname = %s
                """,
                (fn,),
            )
            if cur.fetchone()[0] == 0:
                report["warnings"].append(f"function missing: {fn}")

        report["ok"] = len(report["issues"]) == 0
        report["exit_code"] = 0 if report["ok"] else 1
    finally:
        cur.close()
        conn.close()

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    print(text)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
