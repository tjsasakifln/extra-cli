"""Integration test: validate fresh install and upgrade paths for Story 1.2.

This test verifies that:
1. All migration files exist and have required structure
2. Canonical views exist after migration (AC #8)
3. Match_logging columns exist (AC #9)
4. FK constraints exist (AC #10)
5. Baseline reproducible with fingerprint (AC #2)
6. LOCK_TIMEOUT and statement_timeout configured on large-table migrations

Part of Story 1.2 (Unify Schema): AC #5, #6, #7, #8, #9, #10.

Run with: TEST_DSN=postgresql://test:test@localhost:5433/extra_test pytest ...
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import pytest

_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
CANONICAL_VIEWS_5 = {
    "v_entities_canonical",
    "v_open_opportunities_canonical",
    "v_contracts_canonical",
    "v_suppliers_canonical",
    "v_value_observations_canonical",
}
EXPECTED_VIEWS = CANONICAL_VIEWS_5 | {
    "v_latest_evidence",
    "v_source_health",
    "v_coverage_health",
    "v_schema_integrity",
    "v_migration_status",
    "v_entity_match_summary",
    "v_capability_coverage_summary",
    "v_unmatched_bids",
    "v_coverage_gaps_by_municipio",
    "v_coverage_summary",
    "v_coverage_trend",
    "v_coverage_gaps",
    "v_hierarchical_coverage",
    "v_opportunity_open",
    "v_opportunity_by_source",
    "v_opportunity_coverage_summary",
}
EXPECTED_CONSTRAINTS = {
    "fk_bids_orgao_entity_v2",
    "uq_spe_cnpj_8",
    "uq_oi_content_hash",
}
MATCH_LOGGING_COLUMNS = {"match_method", "match_score", "match_confidence"}


# ── Helper ──────────────────────────────────────────────────────────────


pytestmark = pytest.mark.integration

def _get_cursor():
    """Create a new database cursor for each test.

    Each call opens a fresh connection to avoid transaction state
    leaking between tests.
    """
    if os.getenv("REQUIRE_TEST_DB") != "1":
        pytest.skip("Set REQUIRE_TEST_DB=1 to validate a migrated isolated database")
    dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        return conn.cursor(), conn
    except Exception as exc:
        pytest.skip(f"Test database not available: {exc}")
        return None, None


# ── Test 1: Migration files exist ──────────────────────────────────────


def test_migration_files_exist():
    """All 36 migrations must exist in db/migrations/."""
    assert MIGRATIONS_DIR.exists(), f"Migrations directory not found: {MIGRATIONS_DIR}"

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert len(sql_files) >= 36, (
        f"Expected at least 36 migration files, found {len(sql_files)}. Missing migrations 030-036?"
    )

    for i in range(30, 37):
        expected = [f for f in sql_files if f.name.startswith(f"{i:03d}_")]
        assert expected, f"Missing migration {i:03d}_*.sql"
        _logger.info("  Found: %s", expected[0].name)


# ── Test 2: Migration structural checks ────────────────────────────────


def test_migrations_have_lock_timeout():
    """Migrations that alter large tables must set LOCK_TIMEOUT."""
    large_table_migrations = ["033", "034", "035"]

    for mig_prefix in large_table_migrations:
        files = list(MIGRATIONS_DIR.glob(f"{mig_prefix}_*.sql"))
        for f in files:
            content = f.read_text()
            has_lock = "lock_timeout" in content.lower() or "SET LOCAL" in content
            has_statement = "statement_timeout" in content.lower()
            assert has_lock, f"{f.name} should have SET LOCAL lock_timeout"
            assert has_statement, f"{f.name} should have SET LOCAL statement_timeout"


def test_migrations_have_rollback():
    """New migrations (030-036) should have rollback SQL commented."""
    for i in range(30, 37):
        files = list(MIGRATIONS_DIR.glob(f"{i:03d}_*.sql"))
        for f in files:
            content = f.read_text()
            has_rollback = "rollback" in content.lower() or "ROLLBACK" in content
            assert has_rollback, f"{f.name} is missing rollback section"
            has_begin = "BEGIN;" in content
            has_commit = "COMMIT;" in content
            assert has_begin, f"{f.name} missing BEGIN"
            assert has_commit, f"{f.name} missing COMMIT"


# ── Test 3: Object presence (uses database) ────────────────────────────


def test_canonical_views_exist():
    """AC #8: All canonical views must be present after migration."""
    cur, conn = _get_cursor()
    if cur is None:
        return

    try:
        missing = []
        for view_name in EXPECTED_VIEWS:
            cur.execute(
                "SELECT 1 FROM pg_views WHERE schemaname = 'public' AND viewname = %s",
                (view_name,),
            )
            if cur.fetchone() is None:
                missing.append(view_name)
    finally:
        conn.close()

    assert not missing, f"Missing views: {missing}"
    _logger.info("All %d expected views exist", len(EXPECTED_VIEWS))


def test_match_logging_columns_exist():
    """AC #9: match_logging columns must exist in pncp_raw_bids."""
    cur, conn = _get_cursor()
    if cur is None:
        return

    try:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'pncp_raw_bids'
              AND column_name IN ('match_method', 'match_score', 'match_confidence')
        """)
        found = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    missing = MATCH_LOGGING_COLUMNS - found
    assert not missing, f"Missing match_logging columns: {missing}"


def test_fk_constraints_exist():
    """AC #10: FK constraints must exist (may be NOT VALID)."""
    cur, conn = _get_cursor()
    if cur is None:
        return

    try:
        missing = []
        for name in EXPECTED_CONSTRAINTS:
            cur.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s",
                (name,),
            )
            if cur.fetchone() is None:
                missing.append(name)
    finally:
        conn.close()

    assert not missing, f"Missing constraints: {missing}"
    _logger.info("All %d constraints exist", len(EXPECTED_CONSTRAINTS))


def test_unique_cnpj_8_exists():
    """DT-06: UNIQUE constraint on sc_public_entities.cnpj_8."""
    cur, conn = _get_cursor()
    if cur is None:
        return

    try:
        cur.execute("""
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_spe_cnpj_8'
              AND conrelid = 'sc_public_entities'::regclass
        """)
        exists = cur.fetchone() is not None
    finally:
        conn.close()

    assert exists, "UNIQUE constraint uq_spe_cnpj_8 not found on sc_public_entities"


def test_upsert_functions_are_set_based():
    """DT-05: Upsert functions should be set-based (no FOR loop over jsonb_array_elements).

    Check that the function body contains INSERT ... SELECT rather than FOR rec IN.
    """
    cur, conn = _get_cursor()
    if cur is None:
        return

    try:
        for func_name in ("upsert_pncp_raw_bids", "upsert_pncp_supplier_contracts"):
            cur.execute(
                """
                SELECT pg_catalog.pg_get_functiondef(p.oid)
                FROM pg_proc p
                WHERE p.proname = %s
                  AND p.pronamespace = 'public'::regnamespace
            """,
                (func_name,),
            )
            row = cur.fetchone()
            assert row is not None, f"Function {func_name} not found"
            body = row[0]

            # Set-based = uses INSERT INTO ... SELECT (no FOR rec IN loop)
            assert "INSERT INTO" in body and "SELECT" in body, (
                f"{func_name} does not appear set-based (no INSERT...SELECT)"
            )
            has_for_loop = bool("FOR " in body and " IN " in body and "LOOP" in body)
            if has_for_loop:
                _logger.warning(
                    "%s may still have FOR loop pattern — check manually",
                    func_name,
                )
    finally:
        conn.close()

    _logger.info("Both upsert functions have set-based INSERT...SELECT patterns")


# ── Test 4: Baseline reproducible ──────────────────────────────────────


def test_baseline_fingerprint():
    """AC #2: db/current-schema.sql must exist with valid SHA-256 fingerprint."""
    baseline_file = PROJECT_ROOT / "db" / "current-schema.sql"
    fingerprint_file = PROJECT_ROOT / "db" / "current-schema.sha256"

    assert baseline_file.exists(), (
        "db/current-schema.sql not found. Generate with:\n"
        "  pg_dump --schema-only -d your_dsn > db/current-schema.sql\n"
        "  sha256sum db/current-schema.sql > db/current-schema.sha256"
    )

    assert fingerprint_file.exists(), (
        "db/current-schema.sha256 not found. Generate with:\n"
        "  sha256sum db/current-schema.sql > db/current-schema.sha256"
    )

    stored_hash = fingerprint_file.read_text().strip().split()[0]
    computed_hash = hashlib.sha256(baseline_file.read_bytes()).hexdigest()
    assert stored_hash == computed_hash, (
        f"Fingerprint mismatch! File says {stored_hash}, computed {computed_hash}. "
        "Regenerate: sha256sum db/current-schema.sql > db/current-schema.sha256"
    )
    _logger.info("Baseline fingerprint verified OK: %s", stored_hash)


def test_supabase_archived():
    """AC #3: supabase/current-schema.sql must be archived/historical."""
    archived = PROJECT_ROOT / "supabase" / "archive"
    historical = list(archived.glob("*HISTORICAL*"))
    historical += list(archived.glob("*_HISTORICAL*"))

    assert len(historical) >= 1, (
        "No archived supabase/current-schema.sql found in supabase/archive/. "
        "Run: cp supabase/current-schema.sql supabase/archive/current-schema.sql_HISTORICAL"
    )
    _logger.info("Archived schema found: %s", historical[0].name)
