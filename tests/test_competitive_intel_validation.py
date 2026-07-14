"""Tests for competitive_intel_validation.py — schema validation for competitive intel queries.

The module under test (``scripts/opportunity_intel/competitive_intel_validation.py``)
is a future module that will provide:

- ``validate_competitive_intel_schema(conn)`` — executes 3 queries against
  PostgreSQL and returns a ``SchemaValidation`` dataclass.
- ``SchemaValidation`` — dataclass with fields ``market_share``, ``hhi``,
  ``supplier_ranking``, each a ``CheckResult`` with ``status`` (\"pass\"/\"fail\")
  and ``error_message``.

Tests:
    - ``test_validate_all_queries_pass`` — integration test against real PostgreSQL
    - ``test_validate_detects_column_mismatch`` — unit test with mocked cursor
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


def _competitive_intel_validation():
    """Import the module under test; skip if not yet created."""
    return pytest.importorskip("scripts.opportunity_intel.competitive_intel_validation")


class TestCompetitiveIntelValidation:
    """Schema validation for competitive intelligence queries."""

    @pytest.mark.database
    @pytest.mark.integration
    @pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database integration tests",
    )
    def test_validate_all_queries_pass(self, db_conn):
        """All 3 queries execute successfully against real PostgreSQL.

        Connects via ``db_conn`` fixture (conftest_db.py — session-scoped,
        applies migrations automatically).  Requires a running test database:

            docker compose up -d test-db
            REQUIRE_TEST_DB=1 pytest tests/test_competitive_intel_validation.py -v
        """
        mod = _competitive_intel_validation()
        result = mod.validate_competitive_intel_schema(db_conn)

        assert result.market_share.status == "pass"
        assert result.market_share.error_message == ""
        assert result.hhi.status == "pass"
        assert result.hhi.error_message == ""
        assert result.supplier_ranking.status == "pass"
        assert result.supplier_ranking.error_message == ""

    @pytest.mark.unit
    def test_validate_detects_column_mismatch(self):
        """First query raises UndefinedColumn -> market_share check fails.

        The remaining two queries (hhi, supplier_ranking) continue
        executing and pass normally.  The ``error_message`` on the
        failed check must contain the missing column name.
        """
        import psycopg2

        mod = _competitive_intel_validation()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Query 1: market share  -> UndefinedColumn (column not found)
        # Query 2: HHI           -> success
        # Query 3: ranking       -> success
        mock_cursor.execute.side_effect = [
            psycopg2.errors.UndefinedColumn('column "market_share_value" does not exist'),
            None,
            None,
        ]
        mock_cursor.fetchall.return_value = [("data",)]
        mock_cursor.fetchone.return_value = ("data",)

        result = mod.validate_competitive_intel_schema(mock_conn)

        # Market share check must fail with the column name in the message
        assert result.market_share.status == "fail"
        assert result.market_share.error_message != ""
        assert "market_share_value" in result.market_share.error_message

        # The other two checks must pass unaffected
        assert result.hhi.status == "pass"
        assert result.hhi.error_message == ""
        assert result.supplier_ranking.status == "pass"
        assert result.supplier_ranking.error_message == ""
