"""Pytest configuration — shared fixtures for deterministic tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# real_db: module needs real PostgreSQL when REQUIRE_REAL_DB=1 (full suite).
# Registered here so pytest.ini does not need a new global marker list entry
# if older configs omit it (unknown-mark warning only).
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_db: tests that require a real PostgreSQL connection under REQUIRE_REAL_DB=1",
    )


@pytest.fixture(autouse=True)
def _mock_psycopg2_connect(request):
    """Mock psycopg2.connect to prevent real PostgreSQL calls in tests.

    Tests that call ``compute_readiness()`` trigger ``psycopg2.connect()``
    inside the function for commercial metric queries. This fixture mocks
    it so tests remain deterministic (no real DB dependency).

    Real DB is opt-in (global suite sets REQUIRE_REAL_DB + RESILIENCE_REQUIRE_DB):
    - @pytest.mark.integration + REQUIRE_REAL_DB=1
    - @pytest.mark.database + (REQUIRE_REAL_DB=1 or RESILIENCE_REQUIRE_DB=1)
    - @pytest.mark.real_db + REQUIRE_REAL_DB=1

    Markers alone never open real DB (legacy integration tests mutate tables).
    Blankets without markers keep MagicMock so unit tests cannot wipe suite seeds.
    """
    require_real = os.getenv("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}
    require_resilience_db = os.getenv("RESILIENCE_REQUIRE_DB", "").lower() in {
        "1",
        "true",
        "yes",
    }

    # Real database access is opt-in. Several legacy integration tests mutate
    # shared local tables, so a marker alone must never disable isolation.
    if request.node.get_closest_marker("integration") is not None and require_real:
        yield
        return

    # Pre-VPS resilience vertical slice / DB-marked tests with explicit env.
    if request.node.get_closest_marker("database") is not None and (
        require_resilience_db or require_real
    ):
        yield
        return

    # Explicit marker for modules that need real PG without integration/database.
    if request.node.get_closest_marker("real_db") is not None and require_real:
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

    # National intelligence campaign tests use isolated DSN (port 5435 by default).
    # Allow real PG when test path is tests/national_intel/ and NATIONAL_INTEL_DSN is set
    # (never use HC writer DSN in that package's conftest).
    fspath = str(getattr(request.node, "fspath", "") or getattr(request.node, "path", "") or "")
    if "tests/national_intel" in fspath.replace("\\", "/") and (
        os.getenv("NATIONAL_INTEL_DSN")
        or os.getenv("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}
    ):
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
