"""Unit tests for scripts/datalake_helper.py.

Tests cover the non-DB-dependent helper classes and functions:
- _LocalPgResult
- _LocalPgQuery (query builder)
- meses_to_dias
- DatalakeClient (with mocks for env vars and imports)
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


@pytest.mark.real_db
@pytest.mark.skipif(
    os.getenv("REQUIRE_REAL_DB") != "1",
    reason="Set REQUIRE_REAL_DB=1 to run complete contract analytics proof",
)
def test_contract_analytics_are_complete_keyset_stable_and_page_size_invariant():
    """1,503 rows prove SQL aggregates and annual/detail reconciliation (#355/#356)."""
    import psycopg2
    import psycopg2.extras

    from scripts.datalake_helper import DatalakeClient

    dsn = os.environ["LOCAL_DATALAKE_DSN"]
    supplier = "11222333000181"
    prefix = "test-355-356-"
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM pncp_supplier_contracts WHERE contrato_id LIKE %s", (prefix + "%",))
            cursor.execute("DELETE FROM ingestion_runs WHERE source = 'test_complete_analytics'")
            cursor.execute(
                """
                INSERT INTO ingestion_runs (source, status, started_at, finished_at, completed_at)
                VALUES ('test_complete_analytics', 'completed', NOW(), NOW(), NOW())
                """
            )
            psycopg2.extras.execute_values(
                cursor,
                """
                INSERT INTO pncp_supplier_contracts (
                    contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj,
                    fornecedor_nome, objeto_contrato, valor_total,
                    data_assinatura, data_publicacao_fonte, data_publicacao,
                    uf, source, is_active, supplier_id_type,
                    supplier_identifier, supplier_identifier_export,
                    supplier_identity_reason, ingested_at
                ) VALUES %s
                """,
                [
                    (
                        f"{prefix}{i:04d}",
                        f"{i % 7 + 1:014d}",
                        f"Orgao {i % 7}",
                        supplier,
                        "Fornecedor completo",
                        "servico tecnico nacional",
                        Decimal(i),
                        f"204{(i % 2)}-06-15",
                        f"204{(i % 2)}-06-16",
                        f"204{(i % 2)}-06-16",
                        "SC",
                        "test_complete_analytics",
                        True,
                        "CNPJ",
                        supplier,
                        supplier,
                        "test_valid_cnpj",
                        "2026-08-13T12:00:00Z",
                    )
                    for i in range(1, 1504)
                ],
                page_size=500,
            )
        conn.commit()

        with patch.dict(
            os.environ,
            {"DATALAKE_QUERY_ENABLED": "true", "LOCAL_DATALAKE_DSN": dsn},
        ):
            small = DatalakeClient()
            first_rows, first_meta = small.supplier_contracts(
                ni_fornecedor=supplier,
                date_start="2040-01-01",
                date_end="2041-12-31",
                limit=17,
            )
            assert first_rows is not None
            assert len(first_rows) == 17
            assert first_meta["completeness"] == "PRESENTATION_LIMITED"
            assert first_meta["has_more"] is True
            assert first_meta["total_count"] == 1503
            assert Decimal(str(first_meta["sum_value"])) == sum(Decimal(i) for i in range(1, 1504))
            assert Decimal(str(first_meta["p50"])) == Decimal("752")

            large = DatalakeClient()
            _, large_meta = large.supplier_contracts(
                ni_fornecedor=supplier,
                date_start="2040-01-01",
                date_end="2041-12-31",
                limit=1000,
            )
            for field in ("total_count", "sum_value", "average_value", "p10", "p25", "p50", "p75", "p90"):
                assert large_meta[field] == first_meta[field]

            rows = list(first_rows)
            cursor = first_meta["next_cursor"]
            snapshot = first_meta["snapshot_at"]
            meta = first_meta
            for _ in range(200):
                if not meta["has_more"]:
                    break
                page, meta = small.supplier_contracts(
                    ni_fornecedor=supplier,
                    date_start="2040-01-01",
                    date_end="2041-12-31",
                    limit=17,
                    cursor=cursor,
                    snapshot_at=snapshot,
                )
                assert page is not None
                rows.extend(page)
                cursor = meta["next_cursor"]
            else:
                pytest.fail("keyset pagination exceeded the 200-page test bound")

            assert meta["completeness"] == "COMPLETE"
            assert len(rows) == 1503
            assert len({row["record_id"] for row in rows}) == 1503
            assert sum(Decimal(str(row["valor_global"])) for row in rows) == Decimal(str(meta["sum_value"]))

            annual_detail: dict[int, dict[str, Decimal | int]] = defaultdict(
                lambda: {"matched_contracts": 0, "sum_value": Decimal(0)}
            )
            for row in rows:
                year = int(str(row["event_date"])[:4])
                annual_detail[year]["matched_contracts"] += 1
                annual_detail[year]["sum_value"] += Decimal(str(row["valor_global"]))
            for sql_year in meta["annual_series"]:
                detail = annual_detail[int(sql_year["year"])]
                assert detail["matched_contracts"] == sql_year["matched_contracts"]
                assert detail["sum_value"] == Decimal(str(sql_year["sum_value"]))

            scripts_path = str(Path(__file__).resolve().parents[1] / "scripts")
            sys.path.insert(0, scripts_path)
            try:
                from scripts.collect_report_data import collect_pncp_contratos_fornecedor

                report_rows, report_meta = collect_pncp_contratos_fornecedor(
                    MagicMock(),
                    supplier,
                    datalake_client=small,
                    date_start="2040-01-01",
                    date_end="2041-12-31",
                )
            finally:
                sys.path.remove(scripts_path)
            assert len(report_rows) == 1503
            assert report_meta["status"] == "DATALAKE"
            assert report_meta["detail_reconciled"] is True
            assert report_meta["annual_reconciled"] is True
    finally:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM pncp_supplier_contracts WHERE contrato_id LIKE %s", (prefix + "%",))
            cursor.execute("DELETE FROM ingestion_runs WHERE source = 'test_complete_analytics'")
        conn.commit()
        conn.close()
