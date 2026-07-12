"""Unit tests for scripts/fix/sc_dados_abertos_backfill.py.

Tests cover:
- CNPJ cleaning utility
- Cache load/save
- Brasil API consultation with rate limit, caching, error handling
- Municipio inference across all 3 levels
- Full backfill execution (dry-run and commit modes)
- Report generation
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.fix.sc_dados_abertos_backfill import (
    CACHE_FILE,
    _clean_cnpj,
    _log_attempt,
    consultar_brasil_api,
    generate_report,
    infer_municipio_from_cnpj,
    load_cnpj_cache,
    run_backfill,
    save_cnpj_cache,
)

# ---------------------------------------------------------------------------
# _clean_cnpj
# ---------------------------------------------------------------------------


class TestCleanCNPJ:
    def test_strips_non_digits(self):
        assert _clean_cnpj("12.345.678/0001-99") == "12345678000199"

    def test_preserves_only_digits(self):
        assert _clean_cnpj("82830218000127") == "82830218000127"

    def test_empty_string(self):
        assert _clean_cnpj("") == ""

    def test_handles_spaces_and_letters(self):
        assert _clean_cnpj(" ABC 12.345.678/0001-99 ") == "12345678000199"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestLoadCnpjCache:
    def test_returns_empty_dict_when_file_missing(self, monkeypatch):
        monkeypatch.setattr(CACHE_FILE.__class__, "exists", lambda self: False)
        assert load_cnpj_cache() == {}

    def test_parses_valid_cache(self, tmp_path):
        cache_path = tmp_path / "cnpj_cache.json"
        cache_path.write_text('{"82830218000127": {"municipio": "Floripa"}}')
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("scripts.fix.sc_dados_abertos_backfill.CACHE_FILE", cache_path)
        result = load_cnpj_cache()
        assert result == {"82830218000127": {"municipio": "Floripa"}}
        monkeypatch.undo()

    def test_returns_empty_dict_on_corrupt_json(self, tmp_path):
        cache_path = tmp_path / "cnpj_cache.json"
        cache_path.write_text("{corrupt}")
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("scripts.fix.sc_dados_abertos_backfill.CACHE_FILE", cache_path)
        result = load_cnpj_cache()
        assert result == {}
        monkeypatch.undo()


class TestSaveCnpjCache:
    def test_writes_json_to_file(self, tmp_path):
        cache_path = tmp_path / "cnpj_cache.json"
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr("scripts.fix.sc_dados_abertos_backfill.CACHE_FILE", cache_path)
        data = {"82830218000127": {"municipio": "Floripa"}}
        save_cnpj_cache(data)
        assert cache_path.exists()
        loaded = json.loads(cache_path.read_text())
        assert loaded == data
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# consultar_brasil_api
# ---------------------------------------------------------------------------


class TestConsultarBrasilApi:
    def test_cache_hit_returns_immediately(self):
        """Cache hit must NOT trigger HTTP call."""
        cache = {"82830218000127": {"municipio": "Florianopolis", "codigo_ibge": "4205407"}}
        result = consultar_brasil_api("82830218000127", cache, [0.0])
        assert result == cache["82830218000127"]

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_successful_lookup(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "municipio": "Florianopolis",
            "codigo_municipio_ibge": 4205407,
            "uf": "SC",
        }
        mock_get.return_value = mock_resp

        cache = {}
        result = consultar_brasil_api("82830218000127", cache, [0.0])

        assert result is not None
        assert result["municipio"] == "Florianopolis"
        assert result["codigo_ibge"] == "4205407"
        assert result["uf"] == "SC"
        # Cache should be populated
        assert "82830218000127" in cache
        mock_get.assert_called_once()

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_connection_error_returns_none(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError()

        result = consultar_brasil_api("82830218000127", {}, [0.0])
        assert result is None

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_timeout_returns_none(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout()

        result = consultar_brasil_api("82830218000127", {}, [0.0])
        assert result is None

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_404_sets_negative_cache(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        cache = {}
        result = consultar_brasil_api("82830218000127", cache, [0.0])
        assert result is None
        assert cache.get("82830218000127") is None  # negative cache

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_429_retries_after_backoff(self, mock_get):
        """HTTP 429 should sleep and retry, eventually succeeding."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"municipio": "Sao Jose", "codigo_municipio_ibge": 4205408, "uf": "SC"}
        mock_get.side_effect = [mock_429, mock_200]

        result = consultar_brasil_api("87654321000199", {}, [0.0])
        assert result is not None
        assert result["municipio"] == "Sao Jose"
        assert mock_get.call_count == 2

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_rate_limit_sleeps(self, mock_get):
        """Calls within rate-limit window should sleep."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"municipio": "Test", "codigo_municipio_ibge": 4205409, "uf": "SC"}
        mock_get.return_value = mock_resp

        with patch("scripts.fix.sc_dados_abertos_backfill.time.sleep") as mock_sleep:
            # Set last request to 0.1s ago (below 0.5s min interval)
            consultar_brasil_api("11111111000199", {}, [time.time() - 0.1])
            assert mock_sleep.call_count >= 1

    @patch("scripts.fix.sc_dados_abertos_backfill.requests.get")
    def test_cnpj_with_mask(self, mock_get):
        """CNPJ with mask should be cleaned before API call."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"municipio": "Floripa", "codigo_municipio_ibge": 4205407, "uf": "SC"}
        mock_get.return_value = mock_resp

        result = consultar_brasil_api("82.830.218/0001-27", {}, [0.0])
        assert result is not None
        # Verify the URL used the cleaned CNPJ
        called_url = mock_get.call_args[0][0]
        assert "82830218000127" in called_url


# ---------------------------------------------------------------------------
# infer_municipio_from_cnpj
# ---------------------------------------------------------------------------


class TestInferMunicipio:
    def test_level1_match(self):
        """Level 1: sc_public_entities match produces correct result."""
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("Florianopolis", "4205407")

        result = infer_municipio_from_cnpj("82830218000127", conn, {}, [0.0])
        assert result is not None
        assert result["match_method"] == "sc_public_entities"
        assert result["municipio"] == "Florianopolis"
        assert result["codigo_ibge"] == "4205407"

    def test_level1_no_match_falls_to_level2(self):
        """When Level 1 fails, should attempt Level 2 (Brasil API)."""
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None  # no match in sc_public_entities

        with patch(
            "scripts.fix.sc_dados_abertos_backfill.consultar_brasil_api",
            return_value={"municipio": "Gaspar", "codigo_ibge": "4205902", "uf": "SC"},
        ) as mock_api:
            result = infer_municipio_from_cnpj("99999999000199", conn, {}, [0.0])
            assert result is not None
            assert result["match_method"] == "brasil_api"
            assert result["municipio"] == "Gaspar"
            mock_api.assert_called_once()

    def test_invalid_cnpj_returns_none(self):
        """CNPJ with fewer than 8 digits returns None immediately."""
        conn = MagicMock()
        result = infer_municipio_from_cnpj("123", conn, {}, [0.0])
        assert result is None

    def test_all_levels_fail_returns_none(self):
        """When both Level 1 and Level 2 fail, return None."""
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        with patch(
            "scripts.fix.sc_dados_abertos_backfill.consultar_brasil_api",
            return_value=None,
        ):
            result = infer_municipio_from_cnpj("99999999000199", conn, {}, [0.0])
            assert result is None

    def test_db_error_falls_to_level2(self):
        """DB error at Level 1 should not crash — fall through to Level 2."""
        conn = MagicMock()
        conn.cursor.side_effect = Exception("DB connection lost")

        with patch(
            "scripts.fix.sc_dados_abertos_backfill.consultar_brasil_api",
            return_value={"municipio": "Blumenau", "codigo_ibge": "4202404", "uf": "SC"},
        ) as mock_api:
            result = infer_municipio_from_cnpj("82830218000127", conn, {}, [0.0])
            assert result is not None
            assert result["match_method"] == "brasil_api"
            mock_api.assert_called_once()


# ---------------------------------------------------------------------------
# run_backfill
# ---------------------------------------------------------------------------


class TestRunBackfill:
    @patch("scripts.fix.sc_dados_abertos_backfill.psycopg2.connect")
    def test_dry_run_rolls_back(self, mock_connect):
        """Dry-run mode must call rollback(), not commit()."""
        mock_conn = MagicMock()
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        # Return 1 contract
        mock_cursor.fetchall.side_effect = [
            [(1, "82830218000127", "Orgao Teste")],  # contracts
            [],  # secondary fetch
        ]
        mock_connect.return_value = mock_conn

        with patch(
            "scripts.fix.sc_dados_abertos_backfill.infer_municipio_from_cnpj",
            return_value={"municipio": "Floripa", "codigo_ibge": "4205407", "match_method": "sc_public_entities"},
        ):
            stats = run_backfill(dry_run=True)

        assert stats["total_contratos"] == 1
        assert stats["updated_contratos"] == 1
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

    @patch("scripts.fix.sc_dados_abertos_backfill.psycopg2.connect")
    def test_commit_persists_changes(self, mock_connect):
        """Commit mode must call commit(), not rollback()."""
        mock_conn = MagicMock()
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchall.side_effect = [
            [(1, "82830218000127", "Orgao Teste")],
        ]
        mock_connect.return_value = mock_conn

        with patch(
            "scripts.fix.sc_dados_abertos_backfill.infer_municipio_from_cnpj",
            return_value={"municipio": "Floripa", "codigo_ibge": "4205407", "match_method": "sc_public_entities"},
        ):
            stats = run_backfill(dry_run=False)

        assert stats["updated_contratos"] == 1
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

    @patch("scripts.fix.sc_dados_abertos_backfill.psycopg2.connect")
    def test_handles_db_fetch_exception(self, mock_connect):
        """Database fetch failure should be caught, not crash."""
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("Connection refused")
        mock_connect.return_value = mock_conn

        stats = run_backfill(dry_run=True)
        assert stats["errors"] >= 1
        mock_conn.rollback.assert_called_once()

    @patch("scripts.fix.sc_dados_abertos_backfill.psycopg2.connect")
    def test_counts_failed_inferences(self, mock_connect):
        """Contracts whose CNPJ could not be inferred are counted as failed."""
        mock_conn = MagicMock()
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchall.side_effect = [
            [(1, "00000000000100", "Orgao Sem Match")],
        ]
        mock_connect.return_value = mock_conn

        with patch(
            "scripts.fix.sc_dados_abertos_backfill.infer_municipio_from_cnpj",
            return_value=None,
        ):
            stats = run_backfill(dry_run=True)

        assert stats["failed"] == 1
        assert stats["updated_contratos"] == 0


# ---------------------------------------------------------------------------
# _log_attempt
# ---------------------------------------------------------------------------


class TestLogAttempt:
    def test_inserts_row(self):
        """_log_attempt should execute INSERT SQL."""
        conn = MagicMock()
        _log_attempt(conn, "82830218000127", "sc_public_entities", "Floripa", "4205407", "success")
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.execute.assert_called_once()
        args = cursor.execute.call_args[0][1]
        assert args[0] == "82830218000127"
        assert args[1] == "sc_public_entities"

    def test_handles_db_error_gracefully(self):
        """DB error in _log_attempt should not propagate."""
        conn = MagicMock()
        conn.cursor.side_effect = Exception("DB error")
        # Should not raise
        _log_attempt(conn, "82830218000127", "sc_public_entities", "Floripa", "4205407", "success")


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    @patch("scripts.fix.sc_dados_abertos_backfill.psycopg2.connect")
    def test_returns_summary_dict(self, mock_connect):
        """generate_report runs 3 queries and returns structured dict."""
        mock_conn = MagicMock()
        mock_cm = MagicMock()  # context manager __enter__ return
        mock_conn.cursor.return_value.__enter__.return_value = mock_cm

        # Query 1: contract summary → fetchone
        # Query 2: log breakdown → fetchall
        # Query 3: diagnosis → fetchone
        mock_cm.fetchone.side_effect = [
            (75523, 60000, 15523, 79.5, 400, 50),  # contract summary
            (50, 30, 60.0),  # diagnosis
        ]
        mock_cm.fetchall.side_effect = [
            [("success", 400), ("inference_failed", 50)],  # log breakdown
        ]
        mock_connect.return_value = mock_conn

        report = generate_report()
        assert report["total"] == 75523
        assert report["com_municipio"] == 60000
        assert report["sem_municipio"] == 15523
        assert report["pct_com_municipio"] == 79.5
        assert report["diagnosis"]["total_orgaos"] == 50
        assert report["diagnosis"]["matched_orgaos"] == 30
        assert report["diagnosis"]["match_pct"] == 60.0
        assert report["log_breakdown"]["success"] == 400
        assert report["log_breakdown"]["inference_failed"] == 50
