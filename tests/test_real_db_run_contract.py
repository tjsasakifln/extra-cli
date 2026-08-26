"""Regression contract for issue #285 real_db lifecycle and preflight."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.ops import run_full_suite
from scripts.testing.database_run import (
    REAL_DB_NAME_PREFIX,
    DatabaseRunError,
    assert_generated_database_connection,
    assert_initially_empty,
    generated_database_name,
    require_psycopg2,
    validate_local_admin_dsn,
)
from scripts.testing.real_db_guard import (
    canonical_dsn,
    real_db_skip_is_forbidden,
)


def test_generated_database_names_are_unique_and_safe() -> None:
    first = generated_database_name()
    second = generated_database_name()
    assert first.startswith(REAL_DB_NAME_PREFIX)
    assert second.startswith(REAL_DB_NAME_PREFIX)
    assert first != second


def test_dirty_database_reuse_fails_closed() -> None:
    assert_initially_empty(0, 0)
    with pytest.raises(DatabaseRunError, match="REAL_DB_DIRTY_REUSE"):
        assert_initially_empty(1, 0)
    with pytest.raises(DatabaseRunError, match="REAL_DB_DIRTY_REUSE"):
        assert_initially_empty(0, 1)


def test_destructive_setup_rejects_non_generated_database() -> None:
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = ("extra_test",)
    with pytest.raises(DatabaseRunError, match="REAL_DB_UNSAFE_DATABASE_NAME"):
        assert_generated_database_connection(conn)


def test_required_postgres_tooling_disappearance_is_named() -> None:
    def missing(_name: str):
        raise ModuleNotFoundError("driver removed")

    with pytest.raises(DatabaseRunError, match="REAL_DB_TOOLING_MISSING"):
        require_psycopg2(missing)


def test_admin_dsn_refuses_nonlocal_or_production() -> None:
    with pytest.raises(DatabaseRunError, match="REAL_DB_ISOLATION_FAIL"):
        validate_local_admin_dsn("postgresql://u:p@db.example.com:5432/test")
    with pytest.raises(DatabaseRunError, match="REAL_DB_ISOLATION_FAIL"):
        validate_local_admin_dsn("postgresql://u:p@127.0.0.1:5432/extra_prod")


def test_migration_ledger_missing_or_drifted_fails() -> None:
    expected = {"001": ("001_a.sql", "sha256=aaa")}
    with pytest.raises(RuntimeError, match="REAL_DB_SCHEMA_DRIFT"):
        run_full_suite.compare_migration_ledger(expected, {})
    with pytest.raises(RuntimeError, match="REAL_DB_SCHEMA_DRIFT"):
        run_full_suite.compare_migration_ledger(expected, {"001": ("001_a.sql", "sha256=bbb")})
    run_full_suite.compare_migration_ledger(expected, expected.copy())


def test_missing_mandatory_seed_is_not_a_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_full_suite, "REPO", tmp_path)
    with pytest.raises(FileNotFoundError, match="REAL_DB_SEED_MISSING"):
        run_full_suite.apply_seeds("postgresql://unused")


def test_opted_in_real_db_skip_is_forbidden() -> None:
    assert real_db_skip_is_forbidden(marked_real_db=True, require_real=True)
    assert not real_db_skip_is_forbidden(marked_real_db=True, require_real=False)
    assert not real_db_skip_is_forbidden(marked_real_db=False, require_real=True)


@pytest.mark.real_db
def test_runtime_contract_uses_fresh_migrated_seeded_real_connection() -> None:
    contract = run_full_suite.validate_real_db_contract(canonical_dsn())
    assert contract["connection_kind"] == "psycopg2"
    assert contract["database"].startswith(REAL_DB_NAME_PREFIX)
    assert contract["migration_count"] == len(run_full_suite._expected_migration_ledger())
    assert contract["entity_count"] >= 2085
    assert contract["alias_count"] >= 359
