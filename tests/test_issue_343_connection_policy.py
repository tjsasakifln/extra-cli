"""Refs #343 — required real DSN is never silently replaced by MagicMock.

Drives scripts.testing.connection_policy. The four canonical suites
(concorrentes, valores, idempotency, opportunity integration) share one
admission policy.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.testing.connection_policy import (
    CANONICAL_REAL_SUITES,
    GOLDEN_PATH_TABLES,
    OPPORTUNITY_TABLES,
    connection_kind,
    decide_suite_strategy,
    preflight_tables,
    refuse_silent_mock,
)


class _RealishConn:
    """Minimal stand-in with a psycopg2-like module name."""

    def __init__(self, existing: set[str]) -> None:
        self.existing = existing

    def cursor(self) -> _RealishCursor:
        return _RealishCursor(self.existing)


class _RealishCursor:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self._name = ""

    def __enter__(self) -> _RealishCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, _sql: str, params: tuple[Any, ...] | None = None) -> None:
        self._name = str(params[0]) if params else ""

    def fetchone(self) -> tuple[bool]:
        return (self._name in self.existing,)


def test_issue_343_connection_kind_names_magicmock() -> None:
    assert connection_kind(MagicMock()) == "MagicMock"
    assert connection_kind(None) == "none"


def test_issue_343_refuse_silent_mock_when_required() -> None:
    with pytest.raises(RuntimeError, match="silently replaced by MagicMock"):
        refuse_silent_mock(MagicMock(), required=True, context="concorrentes")


def test_issue_343_refuse_silent_mock_allows_named_real_connection() -> None:
    conn = _RealishConn({"sc_public_entities"})
    # Force module path so connection_kind does not call it MagicMock
    _RealishConn.__module__ = "psycopg2.extensions"
    kind = refuse_silent_mock(conn, required=True, context="valores")
    assert kind == "psycopg2"


def test_issue_343_canonical_suites_never_choose_mock() -> None:
    expected = {
        "test_golden_path_concorrentes_report.py",
        "test_golden_path_valores_report.py",
        "test_golden_path_idempotency.py",
        "test_opportunity_integration.py",
    }
    assert CANONICAL_REAL_SUITES == expected
    for name in expected:
        assert decide_suite_strategy(
            filename=name,
            real_db_marker=False,
            integration_marker=True,
            require_real=True,
            db_available=True,
        ) == "real"
        assert decide_suite_strategy(
            filename=name,
            real_db_marker=False,
            integration_marker=True,
            require_real=False,
            db_available=True,
        ) == "skip"
        assert decide_suite_strategy(
            filename=name,
            real_db_marker=True,
            integration_marker=False,
            require_real=True,
            db_available=False,
        ) == "fail"
        assert decide_suite_strategy(
            filename=name,
            real_db_marker=False,
            integration_marker=False,
            require_real=False,
            db_available=False,
        ) != "mock"


def test_issue_343_unmarked_unit_still_may_mock() -> None:
    assert (
        decide_suite_strategy(
            filename="test_unrelated_unit.py",
            real_db_marker=False,
            integration_marker=False,
            require_real=False,
            db_available=False,
        )
        == "mock"
    )


def test_issue_343_preflight_tables_on_magicmock_is_not_missing_schema() -> None:
    result = preflight_tables(MagicMock(), GOLDEN_PATH_TABLES, context="idempotency")
    assert result.ok is False
    assert result.kind == "MagicMock"
    assert "MagicMock" in result.reason
    assert "missing schema" not in result.reason


def test_issue_343_preflight_tables_reports_missing_and_ready() -> None:
    _RealishConn.__module__ = "psycopg2.extensions"
    missing = preflight_tables(_RealishConn(set()), OPPORTUNITY_TABLES, context="opportunity")
    assert missing.ok is False
    assert set(missing.missing) == set(OPPORTUNITY_TABLES)
    ready = preflight_tables(
        _RealishConn(set(OPPORTUNITY_TABLES)),
        OPPORTUNITY_TABLES,
        context="opportunity",
    )
    assert ready.ok is True
    assert ready.kind == "psycopg2"
