"""Unit + integration tests for idempotent migration apply."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.ops.apply_migrations import (
    _is_repairable_existing,
    list_migrations,
    split_sql,
    version_key,
)

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO / "db" / "migrations"


def test_version_key() -> None:
    assert version_key(Path("001_pncp_raw_bids.sql")) == "001"
    assert version_key(Path("054_local_resilience_contract.sql")) == "054"
    assert version_key(Path("041a_fix_fk_constraints.sql")) == "041a"
    assert version_key(Path("041b_fix_snapshot_membership.sql")) == "041b"
    assert version_key(Path("018-td-5.3_esfera_id_check.sql")) == "018"


def test_list_migrations_sorted_and_capped() -> None:
    files = list_migrations(MIGRATIONS, max_num=5)
    assert files
    assert all(p.name[:3].isdigit() for p in files)
    assert int(files[-1].name[:3]) <= 5
    assert files == sorted(files, key=lambda p: p.name)


def test_split_sql_respects_dollar_quotes() -> None:
    sql = "CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1; END; $$ LANGUAGE plpgsql;"
    stmts = split_sql(sql)
    assert len(stmts) == 1
    assert "PERFORM 1" in stmts[0]


def test_repairable_existing_detection() -> None:
    assert _is_repairable_existing(Exception('relation "pncp_raw_bids" already exists'))
    assert _is_repairable_existing(
        Exception("cannot change return type of existing function")
    )
    assert not _is_repairable_existing(Exception("syntax error at or near X"))


@pytest.mark.integration
@pytest.mark.database
def test_apply_migrations_idempotent_twice() -> None:
    """Requires real PG: REQUIRE_REAL_DB=1 (conftest unmocks psycopg2)."""
    if os.getenv("REQUIRE_REAL_DB") != "1":
        pytest.skip("Set REQUIRE_REAL_DB=1 for live migration idempotency proof")
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("LOCAL_DATALAKE_DSN not set")
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        pytest.skip("psycopg2 missing")

    from scripts.ops.apply_migrations import apply_range

    first = apply_range(dsn, MIGRATIONS, max_num=54, mode="upgrade")
    second = apply_range(dsn, MIGRATIONS, max_num=54, mode="upgrade")
    # Second run must be fully idempotent (skip only)
    assert second["applied"] == [], second
    assert second["repaired"] == [], second
    assert len(second["skipped"]) >= 1
    # First run may apply/repair/skip; total tracked must cover migration files
    total = len(first["applied"]) + len(first["skipped"]) + len(first["repaired"])
    assert total >= len(second["skipped"])
