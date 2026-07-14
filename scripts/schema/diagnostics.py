#!/usr/bin/env python3
"""Schema diagnostics — compares live PostgreSQL schema against expected baseline.

B2G-FIX-04: Validates that every table, column, constraint, and index
referenced by the codebase actually exists in the connected database.

Usage:
    python scripts/schema/diagnostics.py                    # Full report
    python scripts/schema/diagnostics.py --json             # JSON output
    python scripts/schema/diagnostics.py --check-fks        # FK validation only
    python scripts/schema/diagnostics.py --dsn postgresql://...

Exit codes:
    0 — Schema aligned (zero mismatches)
    1 — Schema mismatches found
    2 — Connection or technical failure
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Expected schema baseline (from db/migrations/ 001-041)
# ---------------------------------------------------------------------------

EXPECTED_TABLES: set[str] = {
    "pncp_raw_bids",
    "pncp_supplier_contracts",
    "sc_public_entities",
    "enriched_entities",
    "entity_coverage",
    "entity_hierarchy",
    "ingestion_runs",
    "ingestion_checkpoints",
    "coverage_snapshots",
    "sc_dados_abertos_backfill_log",
    "sc_municipalities",
    "pncp_enrichment_cache",
    "engineering_opportunities",
    "coverage_evidence",
    "opportunity_intel",
    "opportunity_checkpoints",
    "opportunity_runs",
    "opportunity_coverage",
    "contract_version_history",
    "target_universe_runs",
    "target_universe_entities",
    "source_snapshot_membership",
}

EXPECTED_VIEWS: set[str] = {
    # Created by migrations AND consumed by Python code
    "v_unmatched_bids",              # 011, 021a, 021d
    "v_schema_integrity",            # 036
    "v_latest_evidence",             # 024 — consulting_readiness.py
    "v_source_health",               # 024 — consulting_readiness.py
    "v_coverage_gaps_by_municipio",  # 012/020 — local_datalake.py
    "v_contract_historical",         # 026 — contract_intel/cli.py
    "v_supplier_winners",            # 026 — contract_intel/cli.py
    "v_expiring_contracts",          # 026 — contract_intel/cli.py
    "v_contracts_canonical",         # 030 — competitive_intel_validation.py
    "v_opportunity_coverage_summary", # 027 — opportunity_intel/cli.py
    "v_target_universe_active",      # 038 — universe_tools.py
}

# Functions that MUST exist (created by migrations, consumed by code)
EXPECTED_FUNCTIONS: set[str] = {
    "search_datalake",                  # 005/014 — core search
    "upsert_pncp_raw_bids",             # 006/023 — ingest
    "upsert_pncp_supplier_contracts",    # 006 — ingest
    "fn_record_snapshot_membership",     # 039/041b — reconciliation
    "fn_reconcile_source_snapshot",      # 039/041b — reconciliation
    "generate_coverage_snapshot",        # 012/021a — coverage snapshots
}

# FK constraints that MUST be validated (migration 041a)
PENDING_FK_VALIDATION: list[dict[str, str]] = [
    {"table": "pncp_raw_bids", "constraint": "fk_bids_orgao_entity_v2"},
    {"table": "pncp_supplier_contracts", "constraint": "fk_contracts_orgao_entity_v2"},
    {"table": "pncp_supplier_contracts", "constraint": "fk_contracts_supplier_entity_v2"},
]

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres@127.0.0.1:5433/pncp_datalake",
)


@dataclass
class SchemaReport:
    """Result of schema diagnostic run."""

    connected: bool = False
    db_name: str = ""
    migration_count: int = 0
    tables_missing: list[str] = field(default_factory=list)
    tables_extra: list[str] = field(default_factory=list)
    views_missing: list[str] = field(default_factory=list)
    functions_missing: list[str] = field(default_factory=list)
    fks_not_valid: list[dict[str, str]] = field(default_factory=list)
    fks_missing: list[dict[str, str]] = field(default_factory=list)
    critical_findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def aligned(self) -> bool:
        return len(self.tables_missing) == 0 and len(self.fks_not_valid) == 0 and len(self.fks_missing) == 0

    @property
    def exit_code(self) -> int:
        if not self.connected:
            return 2
        return 0 if self.aligned else 1


def run_diagnostics(dsn: str | None = None) -> SchemaReport:
    """Connect to the database and run all diagnostic checks."""
    if psycopg2 is None:
        report = SchemaReport()
        report.critical_findings.append("psycopg2 not installed — cannot connect to database")
        return report

    dsn = dsn or DEFAULT_DSN
    report = SchemaReport()

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        report.connected = True
    except Exception as exc:
        report.critical_findings.append(f"Cannot connect to database: {exc}")
        return report

    try:
        cur = conn.cursor()

        # --- Database info ---
        cur.execute("SELECT current_database()")
        report.db_name = cur.fetchone()[0]

        # --- Migration count ---
        cur.execute("SELECT COUNT(*) FROM _migrations")
        report.migration_count = cur.fetchone()[0]

        # --- Table comparison ---
        cur.execute("""
            SELECT tablename FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        actual_tables = {row[0] for row in cur.fetchall()}

        report.tables_missing = sorted(EXPECTED_TABLES - actual_tables)
        report.tables_extra = sorted(actual_tables - EXPECTED_TABLES)

        # --- View comparison ---
        cur.execute("""
            SELECT viewname FROM pg_catalog.pg_views
            WHERE schemaname = 'public'
            ORDER BY viewname
        """)
        actual_views = {row[0] for row in cur.fetchall()}
        report.views_missing = sorted(EXPECTED_VIEWS - actual_views)

        # --- Function comparison ---
        cur.execute("""
            SELECT routine_name FROM information_schema.routines
            WHERE routine_type = 'FUNCTION'
              AND routine_schema = 'public'
            ORDER BY routine_name
        """)
        actual_functions = {row[0] for row in cur.fetchall()}
        report.functions_missing = sorted(EXPECTED_FUNCTIONS - actual_functions)

        # --- FK validation (migration 041a risk) ---
        for fk in PENDING_FK_VALIDATION:
            cur.execute(
                """
                SELECT convalidated
                FROM pg_catalog.pg_constraint
                WHERE conname = %s
                  AND conrelid = %s::regclass
            """,
                (fk["constraint"], fk["table"]),
            )
            row = cur.fetchone()
            if row is None:
                report.fks_missing.append(fk)
                report.critical_findings.append(
                    f"FK {fk['constraint']} ON {fk['table']} does not exist — migration 041a may not have been applied"
                )
            elif row[0] is False:
                report.fks_not_valid.append(fk)
                report.warnings.append(
                    f"FK {fk['constraint']} ON {fk['table']} is NOT VALID — "
                    f"run VALIDATE CONSTRAINT to enable enforcement"
                )

        # --- Check for stuck ingestion runs ---
        cur.execute("""
            SELECT COUNT(*) FROM ingestion_runs
            WHERE status = 'running'
              AND started_at < NOW() - INTERVAL '4 hours'
        """)
        stuck_runs = cur.fetchone()[0]
        if stuck_runs > 0:
            report.warnings.append(f"{stuck_runs} ingestion runs stuck in 'running' state for >4 hours")

        # --- Check for snapshot reconciliation risk (migration 041b) ---
        cur.execute("""
            SELECT COUNT(*) FROM source_snapshot_membership
            WHERE source_record_id = 'unknown'
        """)
        unknown_records = cur.fetchone()[0]
        if unknown_records > 0:
            report.critical_findings.append(
                f"{unknown_records} source_snapshot_membership rows with "
                f"source_record_id='unknown' — migration 041b key mismatch may "
                f"still be active. Reconciliation may inactivate valid records."
            )

        cur.close()
    except Exception as exc:
        report.critical_findings.append(f"Diagnostic query failed: {exc}")
    finally:
        conn.close()

    return report


def print_report(report: SchemaReport, json_output: bool = False) -> int:
    """Print the diagnostic report and return exit code."""
    if json_output:
        print(
            json.dumps(
                {
                    "connected": report.connected,
                    "db_name": report.db_name,
                    "migration_count": report.migration_count,
                    "aligned": report.aligned,
                    "tables_missing": report.tables_missing,
                    "tables_extra": report.tables_extra,
                    "views_missing": report.views_missing,
                    "functions_missing": report.functions_missing,
                    "fks_not_valid": [f"{fk['constraint']} ON {fk['table']}" for fk in report.fks_not_valid],
                    "fks_missing": [f"{fk['constraint']} ON {fk['table']}" for fk in report.fks_missing],
                    "critical_findings": report.critical_findings,
                    "warnings": report.warnings,
                },
                indent=2,
                default=str,
            )
        )
        return report.exit_code

    # Text output
    print("=" * 60)
    print("SCHEMA DIAGNOSTICS — B2G-FIX-04")
    print("=" * 60)

    if not report.connected:
        print("[FAIL] Cannot connect to database.")
        for finding in report.critical_findings:
            print(f"  CRITICAL: {finding}")
        return 2

    print(f"Database: {report.db_name}")
    print(f"Migrations applied: {report.migration_count}")
    print()

    # Tables
    if report.tables_missing:
        print(f"[FAIL] {len(report.tables_missing)} expected tables missing:")
        for t in report.tables_missing:
            print(f"  - {t}")
    else:
        print("[PASS] All expected tables present.")

    if report.tables_extra:
        print(f"[INFO] {len(report.tables_extra)} extra tables in schema (not in baseline):")
        for t in report.tables_extra:
            print(f"  - {t}")

    # Views
    if report.views_missing:
        print(f"[WARN] {len(report.views_missing)} expected views missing:")
        for v in report.views_missing:
            print(f"  - {v}")
    else:
        print("[PASS] All expected views present.")

    # Functions
    if report.functions_missing:
        print(f"[WARN] {len(report.functions_missing)} expected functions missing:")
        for f in report.functions_missing:
            print(f"  - {f}")
    else:
        print("[PASS] All expected functions present.")

    # FKs
    if report.fks_missing:
        print(f"[FAIL] {len(report.fks_missing)} FK constraints missing (migration 041a?):")
        for fk in report.fks_missing:
            print(f"  - {fk['constraint']} ON {fk['table']}")
    elif report.fks_not_valid:
        print(f"[WARN] {len(report.fks_not_valid)} FK constraints NOT VALID:")
        for fk in report.fks_not_valid:
            print(f"  - {fk['constraint']} ON {fk['table']}")
            print(f"    Fix: ALTER TABLE {fk['table']} VALIDATE CONSTRAINT {fk['constraint']};")
    else:
        print("[PASS] All FK constraints present and validated.")

    # Critical findings
    if report.critical_findings:
        print(f"\n[CRITICAL] {len(report.critical_findings)} critical findings:")
        for f in report.critical_findings:
            print(f"  ! {f}")

    # Warnings
    if report.warnings:
        print(f"\n[WARN] {len(report.warnings)} warnings:")
        for w in report.warnings:
            print(f"  * {w}")

    print()
    if report.aligned:
        print("[RESULT] Schema ALIGNED — zero mismatches.")
    else:
        print("[RESULT] Schema MISMATCHES found — review findings above.")

    return report.exit_code


def main():
    parser = argparse.ArgumentParser(description="Schema diagnostics — B2G-FIX-04")
    parser.add_argument("--dsn", help="PostgreSQL connection string")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--check-fks", action="store_true", help="FK validation only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    report = run_diagnostics(dsn=args.dsn)
    exit_code = print_report(report, json_output=args.json)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
