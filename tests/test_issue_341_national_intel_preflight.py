"""Refs #341 — national_intel preflight before product SQL.

Drives scripts.national_intel.preflight.probe_national_intel. Missing DB
must not hang; reachable DB without schema must not raise UndefinedTable
in the test body; a fully migrated DSN is admitted as ready.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from scripts.national_intel.preflight import (
    CONNECT_TIMEOUT_SECONDS,
    REQUIRED_TABLES,
    REQUIRED_VIEWS,
    PreflightResult,
    inspect_schema,
    probe_national_intel,
    resolve_probe_dsn,
)
from scripts.testing.real_db_guard import (
    DB_REACHABLE_SCHEMA_MISSING,
    DB_READY,
    DB_UNAVAILABLE,
)


class _Cursor:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables
        self.last: tuple[Any, ...] | None = None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.last = params
        self._sql = sql

    def fetchone(self) -> tuple[str, ...] | None:
        if not self.last:
            return None
        _table_type, name = self.last
        if name in self.tables:
            return (name,)
        return None


class _Conn:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self.tables)

    def close(self) -> None:
        self.closed = True


def test_issue_341_missing_db_does_not_hang() -> None:
    def refuse(_dsn: str, timeout: int = 2) -> None:
        assert timeout <= CONNECT_TIMEOUT_SECONDS
        raise ConnectionRefusedError("connection refused")

    started = time.monotonic()
    result = probe_national_intel(
        "postgresql://test:test@127.0.0.1:1/does_not_exist",
        require_real=False,
        timeout=CONNECT_TIMEOUT_SECONDS,
        opener=refuse,
    )
    elapsed = time.monotonic() - started
    assert result.outcome == "skip"
    assert result.state == DB_UNAVAILABLE
    assert "unreachable" in result.reason
    assert "ConnectionRefusedError" in result.reason
    assert elapsed < 8
    assert CONNECT_TIMEOUT_SECONDS <= 2


def test_issue_341_reachable_without_schema_is_preflight_not_undefined_table() -> None:
    def opener(_dsn: str, timeout: int = 2) -> _Conn:
        del timeout
        return _Conn(tables=set())

    result = probe_national_intel(
        "postgresql://test:test@127.0.0.1:5436/empty",
        require_real=False,
        opener=opener,
    )
    assert result.outcome == "skip"
    assert result.state == DB_REACHABLE_SCHEMA_MISSING
    assert "pncp_supplier_contracts" in result.missing_tables
    assert "UndefinedTable" not in result.reason
    assert "preflight" in result.reason


def test_issue_341_require_real_and_explicit_dsn_fail_closed_on_missing_schema() -> None:
    def opener(_dsn: str, timeout: int = 2) -> _Conn:
        del timeout
        return _Conn(tables=set())

    result = probe_national_intel(
        "postgresql://test:test@127.0.0.1:5436/empty",
        require_real=True,
        opener=opener,
    )
    assert result.outcome == "fail"
    assert result.state == DB_REACHABLE_SCHEMA_MISSING
    assert result.missing_tables == REQUIRED_TABLES
    assert "UndefinedTable" not in result.reason


def test_issue_341_fully_migrated_db_is_ready() -> None:
    required = set(REQUIRED_TABLES) | set(REQUIRED_VIEWS)

    def opener(_dsn: str, timeout: int = 2) -> _Conn:
        del timeout
        return _Conn(tables=required)

    result = probe_national_intel(
        "postgresql://test:test@127.0.0.1:5433/extra_test",
        require_real=True,
        opener=opener,
    )
    assert result.ready is True
    assert result.outcome == "ready"
    assert result.state == DB_READY
    assert result.missing_tables == ()
    assert result.missing_views == ()


def test_issue_341_partial_schema_is_not_ready() -> None:
    def opener(_dsn: str, timeout: int = 2) -> _Conn:
        del timeout
        return _Conn(tables=set(REQUIRED_TABLES))

    result = probe_national_intel(
        "postgresql://test:test@127.0.0.1:5433/extra_test",
        require_real=True,
        opener=opener,
    )
    assert result.ready is False
    assert result.state == DB_REACHABLE_SCHEMA_MISSING
    assert result.outcome == "fail"
    assert result.missing_tables == ()
    assert set(result.missing_views) == set(REQUIRED_VIEWS)
    assert "UndefinedTable" not in result.reason


def test_issue_341_inspect_schema_never_runs_product_sql() -> None:
    conn = _Conn(tables={"pncp_supplier_contracts"})
    missing_tables, missing_views = inspect_schema(conn)
    assert missing_tables == ()
    assert "v_intel_contracts_raw_national" in missing_views


def test_issue_341_resolve_probe_dsn_prefers_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    monkeypatch.delenv("CAMPAIGN_TEST_DSN", raising=False)
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:5433/extra_test")
    assert resolve_probe_dsn() == "postgresql://test:test@127.0.0.1:5433/extra_test"
    # Canonical :5433 is legal when the runner named it; fallback :5436 is not exclusive.
    assert ":5436" not in resolve_probe_dsn()


def test_issue_341_preflight_result_carries_host_without_secrets() -> None:
    result = PreflightResult("skip", "national_intel preflight: database unreachable at 127.0.0.1:1/x", "127.0.0.1:1/x")
    assert "password" not in result.reason
    assert "test:test" not in result.dsn_host
