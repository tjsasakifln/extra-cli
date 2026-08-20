"""Gating tests for named real_db admission (issues #285 #341 #343).

Drives scripts.testing.real_db_guard.probe_database / apply_admission.
MagicMock is never accepted as SQL. UndefinedTable is not the schema signal.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.testing.connection_policy import (
    GOLDEN_PATH_TABLES,
    IDEMPOTENCY_TABLES,
    OPPORTUNITY_TABLES,
)
from scripts.testing.real_db_guard import (
    CONNECT_TIMEOUT_SECONDS,
    DB_REACHABLE_SCHEMA_MISSING,
    DB_READY,
    DB_UNAVAILABLE,
    apply_admission,
    canonical_dsn,
    connection_kind,
    dsn_host_for_logs,
    probe_database,
    refuse_magic_mock_sql,
)


class _Cursor:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables
        self.last: tuple[Any, ...] | None = None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.last = params

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


_Conn.__module__ = "psycopg2.extensions"


def test_magicmock_is_unavailable_not_schema_missing() -> None:
    def opener(_dsn: str, **_kwargs: object) -> MagicMock:
        return MagicMock()

    result = probe_database(
        "postgresql://test:test@127.0.0.1:5433/extra_test",
        opener=opener,
        required_tables=GOLDEN_PATH_TABLES,
        context="concorrentes",
    )
    assert result.state == DB_UNAVAILABLE
    assert result.kind == "MagicMock"
    assert "MagicMock" in result.reason
    assert result.state != DB_REACHABLE_SCHEMA_MISSING
    assert "UndefinedTable" not in result.reason
    with pytest.raises(RuntimeError, match="MagicMock"):
        refuse_magic_mock_sql(MagicMock(), context="valores")


def test_require_real_db_unreachable_is_fail_not_skip() -> None:
    def refuse(_dsn: str, **kwargs: object) -> None:
        timeout = kwargs.get("connect_timeout", kwargs.get("timeout", 2))
        assert int(timeout) <= CONNECT_TIMEOUT_SECONDS
        raise ConnectionRefusedError("connection refused")

    result = probe_database(
        "postgresql://test:test@127.0.0.1:1/does_not_exist",
        timeout=CONNECT_TIMEOUT_SECONDS,
        opener=refuse,
        context="real_db",
    )
    assert result.state == DB_UNAVAILABLE
    assert "ConnectionRefusedError" in result.reason
    assert "password" not in result.reason
    assert "test:test" not in result.host
    with pytest.raises(pytest.fail.Exception, match=DB_UNAVAILABLE):
        apply_admission(result, require_real=True)
    with pytest.raises(pytest.skip.Exception, match=DB_UNAVAILABLE):
        apply_admission(result, require_real=False)


def test_empty_schema_is_reachable_schema_missing() -> None:
    def opener(_dsn: str, **_kwargs: object) -> _Conn:
        return _Conn(tables=set())

    result = probe_database(
        "postgresql://test:test@127.0.0.1:5433/empty",
        opener=opener,
        required_tables=OPPORTUNITY_TABLES,
        context="opportunity",
    )
    assert result.state == DB_REACHABLE_SCHEMA_MISSING
    assert set(result.missing) == set(OPPORTUNITY_TABLES)
    assert "UndefinedTable" not in result.reason
    assert result.kind == "psycopg2"
    with pytest.raises(pytest.fail.Exception, match=DB_REACHABLE_SCHEMA_MISSING):
        apply_admission(result, require_real=True)
    with pytest.raises(pytest.skip.Exception, match=DB_REACHABLE_SCHEMA_MISSING):
        apply_admission(result, require_real=False)


def test_partial_schema_is_not_ready() -> None:
    def opener(_dsn: str, **_kwargs: object) -> _Conn:
        return _Conn(tables={"sc_public_entities"})

    result = probe_database(
        "postgresql://test:test@127.0.0.1:5433/partial",
        opener=opener,
        required_tables=IDEMPOTENCY_TABLES,
        context="idempotency",
    )
    assert result.state == DB_REACHABLE_SCHEMA_MISSING
    assert "pncp_raw_bids" in result.missing
    assert "sc_public_entities" not in result.missing
    assert "UndefinedTable" not in result.reason


def test_fully_migrated_schema_is_ready() -> None:
    required = set(GOLDEN_PATH_TABLES)

    def opener(_dsn: str, **_kwargs: object) -> _Conn:
        return _Conn(tables=required)

    result = probe_database(
        "postgresql://test:test@127.0.0.1:5433/extra_test",
        opener=opener,
        required_tables=GOLDEN_PATH_TABLES,
        context="concorrentes",
    )
    assert result.state == DB_READY
    assert result.ready is True
    assert result.kind == "psycopg2"
    assert result.missing == ()
    apply_admission(result, require_real=True)


def test_connection_kind_names_driver_not_magicmock() -> None:
    conn = _Conn(tables=set(GOLDEN_PATH_TABLES))
    assert connection_kind(conn) == "psycopg2"
    assert connection_kind(MagicMock()) == "MagicMock"
    assert refuse_magic_mock_sql(conn, context="valores") == "psycopg2"


def test_canonical_dsn_prefers_database_url_not_5436(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    monkeypatch.delenv("CAMPAIGN_TEST_DSN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:5433/extra_test")
    dsn = canonical_dsn()
    assert dsn == "postgresql://test:test@127.0.0.1:5433/extra_test"
    assert ":5436" not in dsn
    host = dsn_host_for_logs(dsn)
    assert "password" not in host
    assert "test:test" not in host
    assert "5433" in host


def test_optional_mode_skip_reason_is_named() -> None:
    result = probe_database(
        "postgresql://test:test@127.0.0.1:1/x",
        opener=lambda *_a, **_k: (_ for _ in ()).throw(ConnectionRefusedError("no")),
        context="real_db",
    )
    assert result.state == DB_UNAVAILABLE
    with pytest.raises(pytest.skip.Exception, match=rf"{DB_UNAVAILABLE}:"):
        apply_admission(result, require_real=False)
