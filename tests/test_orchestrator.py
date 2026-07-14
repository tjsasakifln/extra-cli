"""Unit tests for scripts/crawl/orchestrator.py.

Tests cover the orchestration logic using mocked database
connections and dynamically-loaded crawler modules.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Patch DEFAULT_DSN on config.settings before importing orchestrator.
# The orchestrator imports ``DEFAULT_DSN`` from ``config.settings`` but
# this constant was never defined in the settings module (known gap).
# We inject it here so the test can import the orchestrator module.
#
# Also pre-register mocks for modules that are either missing or would
# trigger real database connections at import time.
# ---------------------------------------------------------------------------
import config.settings

config.settings.DEFAULT_DSN = "postgresql://test:test@localhost/test"

# Pre-register mocks for modules with external dependencies
_sys_mocks = {}

for _mod_name in ("supabase_client", "scripts.crawl.checkpoint"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

sys.modules["scripts.crawl.checkpoint"].save_checkpoint = MagicMock()
sys.modules["scripts.crawl.checkpoint"].is_crawl_completed_today = MagicMock()

from scripts.crawl.orchestrator import (  # noqa: E402
    _finish_ingestion_run,
    _get_conn,
    _start_ingestion_run,
    crawl_source,
    load_crawler,
    load_entities,
)

# ---------------------------------------------------------------------------
# _get_conn
# ---------------------------------------------------------------------------
# Note: _get_conn() does ``import psycopg2`` inside the function, not at
# module level. We patch the top-level ``psycopg2.connect`` instead of
# a module attribute on orchestrator.


@patch("psycopg2.connect")
class TestGetConn:
    def test_returns_connection(self, mock_connect):
        """_get_conn() creates a psycopg2 connection with DEFAULT_DSN."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = _get_conn()

        mock_connect.assert_called_once_with("postgresql://test:test@localhost/test")
        assert result == mock_conn


# ---------------------------------------------------------------------------
# _start_ingestion_run
# ---------------------------------------------------------------------------


class TestStartIngestionRun:
    def test_returns_run_id(self):
        """_start_ingestion_run() inserts a row and returns the ID."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = (42,)

        run_id = _start_ingestion_run(conn, "pncp")

        assert run_id == 42
        cursor.execute.assert_called_once()
        conn.commit.assert_called_once()
        cursor.close.assert_called_once()


# ---------------------------------------------------------------------------
# _finish_ingestion_run
# ---------------------------------------------------------------------------


class TestFinishIngestionRun:
    def test_updates_run_with_stats(self):
        """_finish_ingestion_run() updates ingestion_runs with provided stats."""
        conn = MagicMock()
        cursor = conn.cursor.return_value

        _finish_ingestion_run(conn, run_id=42, fetched=100, upserted=80, covered=60)

        cursor.execute.assert_called_once()
        conn.commit.assert_called_once()
        cursor.close.assert_called_once()

    def test_default_status_is_completed(self):
        """Default status is 'completed' when not specified."""
        conn = MagicMock()
        cursor = conn.cursor.return_value

        _finish_ingestion_run(conn, run_id=1, fetched=0, upserted=0, covered=0)

        sql = cursor.execute.call_args[0][0]
        assert "UPDATE ingestion_runs" in sql

    def test_failed_status_with_error(self):
        """Error message is included when status is 'failed'."""
        conn = MagicMock()
        cursor = conn.cursor.return_value

        _finish_ingestion_run(
            conn, run_id=5, fetched=0, upserted=0, covered=0, status="failed", error="Connection timeout"
        )

        params = cursor.execute.call_args[0][1]
        # Params order: (fetched, upserted, covered, status, error, run_id)
        assert params[3] == "failed"
        assert params[4] == "Connection timeout"


# ---------------------------------------------------------------------------
# load_entities
# ---------------------------------------------------------------------------


class TestLoadEntities:
    def test_returns_list_of_entities(self):
        """load_entities() returns entities from the database."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.description = [
            ("id", None, None, None, None, None, None),
            ("razao_social", None, None, None, None, None, None),
            ("cnpj_8", None, None, None, None, None, None),
            ("municipio", None, None, None, None, None, None),
            ("codigo_ibge", None, None, None, None, None, None),
            ("natureza_juridica", None, None, None, None, None, None),
            ("raio_200km", None, None, None, None, None, None),
        ]
        cursor.fetchall.return_value = [
            (1, "PREFEITURA MUNICIPAL DE FLORIANOPOLIS", "12345678", "Florianopolis", "4205407", "PREFEITURA", True),
        ]

        entities = load_entities(conn)

        assert len(entities) == 1
        assert entities[0]["id"] == 1
        assert entities[0]["razao_social"] == "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"
        assert entities[0]["cnpj_8"] == "12345678"
        cursor.close.assert_called_once()

    def test_empty_result(self):
        """Return empty list when no entities exist."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.description = [("id", None, None, None, None, None, None)]
        cursor.fetchall.return_value = []

        entities = load_entities(conn)

        assert entities == []

    def test_within_200km_only(self):
        """Filter entities within 200km when parameter is True."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.description = [("id", None, None, None, None, None, None)]
        cursor.fetchall.return_value = []

        load_entities(conn, within_200km_only=True)

        sql = cursor.execute.call_args[0][0]
        assert "raio_200km = TRUE" in sql


# ---------------------------------------------------------------------------
# load_crawler
# ---------------------------------------------------------------------------


class TestLoadCrawler:
    def test_loads_known_source(self):
        """Return a module for known source 'pncp'."""
        module = load_crawler("pncp")
        assert module is not None

    def test_returns_none_for_unknown_source(self):
        """Return None for unknown source."""
        module = load_crawler("unknown_source")
        assert module is None

    def test_pncp_crawler_has_expected_attrs(self):
        """Loaded crawler module has crawl and transform functions."""
        module = load_crawler("pncp")
        assert hasattr(module, "crawl")
        assert hasattr(module, "transform")

    def test_dom_sc_crawler_loads(self):
        """DOM-SC crawler module loads successfully."""
        module = load_crawler("dom_sc")
        assert module is not None

    def test_contracts_crawler_loads(self):
        """Contracts crawler module loads successfully."""
        module = load_crawler("contracts")
        assert module is not None

    def test_cache_miss_without_raising(self):
        """Unknown source returns None without raising."""
        module = load_crawler("nonexistent")
        assert module is None


# ---------------------------------------------------------------------------
# crawl_source
# ---------------------------------------------------------------------------
# All crawl_source tests need both _get_conn and load_crawler mocked to
# avoid real database connections.

_BASE_CURSOR_DESCRIPTION = [("upsert_result", None, None, None, None, None, None)]


class TestCrawlSource:
    @patch("scripts.crawl.orchestrator.load_crawler")
    @patch("scripts.crawl.orchestrator._get_conn")
    def test_unknown_source_returns_skipped(self, mock_get_conn, mock_load_crawler):
        """Unknown source returns status 'skipped' when crawler module missing."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = (1,)

        mock_load_crawler.return_value = None  # Simulate unknown source

        result = crawl_source("unknown_source", [], mode="full")

        assert result["status"] == "skipped"
        assert "error" in result

    @patch("scripts.crawl.orchestrator.load_crawler")
    @patch("scripts.crawl.orchestrator._get_conn")
    @patch("scripts.matching.entity_matcher.match_entities_cascade")
    def test_successful_crawl_returns_ok(self, mock_match, mock_get_conn, mock_load_crawler):
        """Successful full crawl returns status 'ok' with counts."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = (1,)  # run_id
        mock_cursor.fetchall.return_value = [("inserted",)]
        mock_cursor.description = _BASE_CURSOR_DESCRIPTION
        mock_match.return_value = {"cnpj": 1, "name_normalized": 0, "fuzzy": 0, "unmatched": 0, "total": 1}

        mock_crawler = MagicMock()
        mock_crawler.crawl.return_value = [{"id": "1"}]
        mock_crawler.transform.return_value = [{"pncp_id": "1", "objeto_compra": "test"}]
        mock_load_crawler.return_value = mock_crawler

        result = crawl_source("pncp", [], mode="full")

        assert result["status"] == "ok"
        assert result["fetched"] == 1
        assert result["upserted"] == 1

    @patch("scripts.crawl.orchestrator.load_crawler")
    @patch("scripts.crawl.orchestrator._get_conn")
    def test_no_records_fetched(self, mock_get_conn, mock_load_crawler):
        """Return ok when crawler finds no records."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = (1,)

        mock_crawler = MagicMock()
        mock_crawler.crawl.return_value = []
        mock_load_crawler.return_value = mock_crawler

        result = crawl_source("pncp", [], mode="full")

        assert result["status"] == "ok"
        assert result["fetched"] == 0
        assert result["upserted"] == 0

    @patch("scripts.crawl.orchestrator.load_crawler")
    @patch("scripts.crawl.orchestrator._get_conn")
    def test_upsert_exception_returns_failed(self, mock_get_conn, mock_load_crawler):
        """Database error during upsert returns status 'failed'."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = (1,)

        # First execute (from _start_ingestion_run) succeeds
        # Second execute (from upsert) fails
        mock_cursor.execute.side_effect = [None, Exception("DB error")]

        mock_crawler = MagicMock()
        mock_crawler.crawl.return_value = [{"id": "1"}]
        mock_crawler.transform.return_value = [{"pncp_id": "1"}]
        mock_load_crawler.return_value = mock_crawler

        result = crawl_source("pncp", [], mode="full")

        assert result["status"] == "failed"
        assert "error" in result

    @patch("scripts.crawl.orchestrator.load_crawler")
    @patch("scripts.crawl.orchestrator._get_conn")
    @patch("scripts.matching.entity_matcher.match_entities_cascade")
    def test_entity_matching_not_called_for_contracts(self, mock_match, mock_get_conn, mock_load_crawler):
        """Entity matching is skipped for contracts source."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = (1,)
        mock_cursor.fetchall.return_value = [("inserted",)]
        mock_cursor.description = _BASE_CURSOR_DESCRIPTION

        mock_crawler = MagicMock()
        mock_crawler.crawl.return_value = [{"id": "1"}]
        mock_crawler.transform.return_value = [{"pncp_id": "1", "objeto_compra": "test"}]
        mock_load_crawler.return_value = mock_crawler

        result = crawl_source("contracts", [])

        mock_match.assert_not_called()
        assert result["status"] == "ok"

    @patch("scripts.crawl.orchestrator.load_crawler")
    @patch("scripts.crawl.orchestrator._get_conn")
    def test_dsn_override(self, mock_get_conn, mock_load_crawler):
        """DSN override works without error."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = (1,)

        mock_crawler = MagicMock()
        mock_crawler.crawl.return_value = []
        mock_load_crawler.return_value = mock_crawler

        result = crawl_source("pncp", [], dsn="postgresql://override:test@localhost/test")

        assert result["status"] == "ok"
