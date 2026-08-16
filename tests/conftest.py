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

    # Decision & Outcome Memory v1: persistence proofs require real PostgreSQL
    # (campaign EXTRA-DECISION-OUTCOME-MEMORY-01). Never mock this suite.
    fspath = str(getattr(request.node, "fspath", "") or getattr(request.node, "path", ""))
    path_parts = fspath.replace("\\", "/").split("/")
    if "decision_memory" in path_parts:
        yield
        return

    # CONFENGE target-fit continuous refresh integration tests already skip without
    # DSN. They prove SKIP LOCKED, publish atomicity, downgrade→send-ready, etc.
    if "confenge_target_fit" in path_parts:
        yield
        return

    # Durable contact-discovery batch proves SKIP LOCKED / lease / resume on real PG.
    if "test_contact_discovery_batch.py" in path_parts:
        yield
        return

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
    # #285: real_db never falls through to MagicMock. Missing opt-in is skip
    # or a configuration error, not a silently mocked missing table.
    # #343: the four canonical suites that consult PostgreSQL share that policy
    # even if a file still carries only @pytest.mark.integration.
    from scripts.testing.connection_policy import (
        CANONICAL_REAL_SUITES,
        decide_suite_strategy,
    )

    filename = path_parts[-1] if path_parts else ""
    consults_pg = request.node.get_closest_marker("real_db") is not None or (
        filename in CANONICAL_REAL_SUITES
    )
    if consults_pg:
        from scripts.testing.real_db_guard import admit_real_db_or_raise

        admit_real_db_or_raise(real_db_marker=True, require_real=require_real)
        yield
        return

    if request.node.get_closest_marker("integration") is not None:
        from scripts.testing.real_db_guard import dsn_is_reachable

        strategy = decide_suite_strategy(
            filename=filename,
            real_db_marker=False,
            integration_marker=True,
            require_real=require_real,
            db_available=dsn_is_reachable() if require_real else False,
        )
        if strategy == "real":
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
