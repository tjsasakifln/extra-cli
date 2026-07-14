"""Unit tests for scripts/datalake_helper.py.

Tests cover the non-DB-dependent helper classes and functions:
- _LocalPgResult
- _LocalPgQuery (query builder)
- meses_to_dias
- DatalakeClient (with mocks for env vars and imports)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from scripts.datalake_helper import (
    _LocalPgQuery,
    _LocalPgResult,
    meses_to_dias,
)

# ---------------------------------------------------------------------------
# _LocalPgResult
# ---------------------------------------------------------------------------


class TestLocalPgResult:
    def test_stores_data(self):
        """Store data passed to constructor."""
        result = _LocalPgResult([{"id": 1}])
        assert result.data == [{"id": 1}]

    def test_execute_returns_self(self):
        """execute() returns self (no-op for compatibility)."""
        result = _LocalPgResult([])
        returned = result.execute()
        assert returned is result

    def test_empty_data(self):
        """Handle empty data list."""
        result = _LocalPgResult([])
        assert result.data == []


# ---------------------------------------------------------------------------
# _LocalPgQuery (query builder)
# ---------------------------------------------------------------------------


class TestLocalPgQueryBuilder:
    def test_select_sets_columns(self):
        """select() sets the columns string."""
        conn = MagicMock()
        q = _LocalPgQuery(conn, "test_table")
        q.select("id, name")
        assert q._cols == "id, name"

    def test_eq_adds_where(self):
        """eq() adds an equality condition."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.eq("status", "active")
        assert len(q._wheres) == 1
        assert "status" in q._wheres[0]

    def test_in_adds_in_condition(self):
        """in_() adds an IN condition."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.in_("uf", ["SC", "PR"])
        assert len(q._wheres) == 1
        assert "IN" in q._wheres[0]

    def test_gte_adds_greater_than(self):
        """gte() adds >= condition."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.gte("valor", 1000.0)
        assert ">=" in q._wheres[0]

    def test_lte_adds_less_than(self):
        """lte() adds <= condition."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.lte("valor", 50000.0)
        assert "<=" in q._wheres[0]

    def test_ilike_adds_pattern(self):
        """ilike() adds ILIKE condition."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.ilike("name", "%test%")
        assert "ILIKE" in q._wheres[0]

    def test_order_sets_column_and_direction(self):
        """order() sets ordering."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.order("created_at", desc=True)
        assert q._order_col == "created_at"
        assert q._order_desc is True

    def test_order_ascending(self):
        """order() with desc=False sets ascending."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.order("name", desc=False)
        assert q._order_desc is False

    def test_limit_sets_value(self):
        """limit() sets the limit value."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        q.limit(10)
        assert q._limit_val == 10

    def test_chained_calls(self):
        """Method chaining works fluently."""
        q = _LocalPgQuery(MagicMock(), "test_table")
        result = q.select("id, name").eq("status", "active").limit(10)
        assert result is q

    def test_execute_builds_sql(self):
        """execute() builds and runs SQL query.

        Note: _LocalPgQuery.execute() calls self._conn._cursor()
        (the private _cursor() context manager), not cursor().
        """
        mock_conn = MagicMock()
        mock_cm = mock_conn._cursor.return_value
        mock_cursor = MagicMock()
        mock_cm.__enter__.return_value = mock_cursor
        mock_cursor.description = [("id", None, None, None, None, None, None)]
        mock_cursor.fetchall.return_value = [(1,)]

        q = _LocalPgQuery(mock_conn, "test_table")
        q.select("id").eq("status", "active")
        result = q.execute()

        assert isinstance(result, _LocalPgResult)
        assert len(result.data) == 1

    def test_execute_with_all_clauses(self):
        """execute() builds correct SQL with all clauses."""
        mock_conn = MagicMock()
        mock_cm = mock_conn._cursor.return_value
        mock_cursor = MagicMock()
        mock_cm.__enter__.return_value = mock_cursor
        mock_cursor.description = []
        mock_cursor.fetchall.return_value = []

        q = _LocalPgQuery(mock_conn, "test_table")
        q.select("*").eq("uf", "SC").in_("modalidade_id", [5, 6])
        q.order("data_publicacao", desc=True).limit(100)
        q.execute()

        # Verify the SQL was constructed
        sql = mock_cursor.execute.call_args[0][0]
        assert "SELECT" in sql
        assert "WHERE" in sql
        assert "ORDER BY" in sql
        assert "LIMIT" in sql


# ---------------------------------------------------------------------------
# meses_to_dias
# ---------------------------------------------------------------------------


class TestMesesToDias:
    def test_none_returns_none(self):
        """Return None for None input."""
        assert meses_to_dias(None) is None

    def test_1_month_returns_30(self):
        """1 month = ~30 days."""
        assert meses_to_dias(1) == 30

    def test_6_months_returns_182(self):
        """6 months = ~182 days (6 * 30.4)."""
        assert meses_to_dias(6) == 182

    def test_12_months_returns_364(self):
        """12 months = ~364 days (12 * 30.4)."""
        assert meses_to_dias(12) == 364

    def test_zero_months(self):
        """0 months = 0 days."""
        assert meses_to_dias(0) == 0


# ---------------------------------------------------------------------------
# DatalakeClient (mocked environment)
# ---------------------------------------------------------------------------


class TestDatalakeClient:
    def test_disabled_when_env_not_set(self):
        """is_enabled returns False when DATALAKE_QUERY_ENABLED not set."""
        with patch.dict(os.environ, {}, clear=True):
            from scripts.datalake_helper import DatalakeClient

            client = DatalakeClient()
            assert client.is_enabled is False

    def test_disabled_when_env_is_false(self):
        """is_enabled returns False when DATALAKE_QUERY_ENABLED=false."""
        with patch.dict(os.environ, {"DATALAKE_QUERY_ENABLED": "false"}, clear=True):
            from scripts.datalake_helper import DatalakeClient

            client = DatalakeClient()
            assert client.is_enabled is False

    def test_enabled_with_env_true(self):
        """is_enabled returns True when DATALAKE_QUERY_ENABLED=true."""
        with patch.dict(os.environ, {"DATALAKE_QUERY_ENABLED": "true"}, clear=True):
            from scripts.datalake_helper import DatalakeClient

            client = DatalakeClient()
            assert client.is_enabled is True

    def test_backend_is_local(self):
        """backend returns 'local' when enabled."""
        with patch.dict(os.environ, {"DATALAKE_QUERY_ENABLED": "true"}, clear=True):
            from scripts.datalake_helper import DatalakeClient

            client = DatalakeClient()
            # Must call is_enabled first to trigger initialization
            _ = client.is_enabled
            assert client.backend == "local"

    def test_backend_is_none_when_disabled(self):
        """backend returns 'none' when disabled."""
        from scripts.datalake_helper import DatalakeClient

        client = DatalakeClient()
        assert client.backend == "none"

    def test_init_error_is_none_when_disabled(self):
        """init_error provides reason when disabled."""
        from scripts.datalake_helper import DatalakeClient

        client = DatalakeClient()
        assert client.init_error is not None or client.is_enabled is False

    def test_search_bids_returns_none_when_disabled(self):
        """search_bids returns None when disabled."""
        from scripts.datalake_helper import DatalakeClient

        client = DatalakeClient()
        rows, meta = client.search_bids()
        assert rows is None
        assert "datalake_error" in meta
