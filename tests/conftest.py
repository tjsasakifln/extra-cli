"""Pytest configuration — shared fixtures for deterministic tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_psycopg2_connect(request):
    """Mock psycopg2.connect to prevent real PostgreSQL calls in tests.

    Tests that call ``compute_readiness()`` trigger ``psycopg2.connect()``
    inside the function for commercial metric queries. This fixture mocks
    it so tests remain deterministic (no real DB dependency).

    Excludes ``TestPostgreSQLFailClosed`` which explicitly tests connection
    failure behavior.
    """
    # Real database access is opt-in. Several legacy integration tests mutate
    # shared local tables, so a marker alone must never disable isolation.
    if request.node.get_closest_marker("integration") is not None and os.getenv("REQUIRE_REAL_DB") == "1":
        yield
        return

    # Pre-VPS resilience vertical slice needs a real PostgreSQL connection.
    if request.node.get_closest_marker("database") is not None and os.getenv(
        "RESILIENCE_REQUIRE_DB", ""
    ).lower() in {"1", "true", "yes"}:
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
