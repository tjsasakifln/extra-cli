"""Pytest configuration — shared fixtures for deterministic tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def _dsn_configured() -> bool:
    return bool(os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN"))


@pytest.fixture(autouse=True)
def _mock_psycopg2_connect(request):
    """Mock psycopg2.connect to prevent accidental real PostgreSQL in unit tests.

    Real DB is used when:
    - ``REQUIRE_REAL_DB=1`` and test is marked ``integration``; or
    - ``RESILIENCE_REQUIRE_DB=1`` (or true/yes) and test is marked ``database``; or
    - CI full suite with a configured DSN and test is marked ``integration`` or
      ``database`` (so migrations applied in the job are actually exercised).

    Unit tests without those markers remain mocked and deterministic.
    """
    marked_integration = request.node.get_closest_marker("integration") is not None
    marked_database = request.node.get_closest_marker("database") is not None
    allow_real = False
    if marked_integration and (_env_truthy("REQUIRE_REAL_DB") or (_env_truthy("CI") and _dsn_configured())):
        allow_real = True
    if marked_database and (
        _env_truthy("RESILIENCE_REQUIRE_DB") or (_env_truthy("CI") and _dsn_configured())
    ):
        allow_real = True
    if allow_real:
        yield
        return

    # Allow TestPostgreSQLFailClosed to test real connection failures
    cls = getattr(request, "cls", None)
    if cls is not None and cls.__name__ == "TestPostgreSQLFailClosed":
        yield
        return

    # Explicit real-connection negative paths (broken DSN / fail-closed)
    if request.node.name in {
        "test_snapshot_step_handles_missing_tables",
    }:
        yield
        return

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = [0]
    mock_cursor.description = []

    with patch("psycopg2.connect", return_value=mock_conn):
        yield
