"""Tests for FetchResult/FetchStatus, checkpoint, and error discrimination.

Covers goal criteria:
  - FetchResult distinguishes zero-real from connection/HTTP/parse failure
  - Checkpoint save/load/reentrant skip
  - Exception → empty list is PROHIBITED
  - UF is never presumed "SC"
"""

import json
import os
import tempfile
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from scripts.crawl.contracts_crawler import (
    CrawlCheckpoint,
    FetchResult,
    FetchStatus,
    _fetch_page,
    _transform_record,
    load_checkpoint,
    save_checkpoint,
)

# ---------------------------------------------------------------------------
# FetchStatus tests
# ---------------------------------------------------------------------------


class TestFetchStatus:
    """FetchStatus enum discriminates all failure modes."""

    def test_all_statuses_distinct(self):
        """All FetchStatus values must be distinct."""
        values = [s.value for s in FetchStatus]
        assert len(values) == len(set(values)), f"Duplicate values: {values}"

    def test_success_zero_differs_from_connection_failed(self):
        """SUCCESS_ZERO (API said zero) ≠ CONNECTION_FAILED (couldn't reach API)."""
        assert FetchStatus.SUCCESS_ZERO != FetchStatus.CONNECTION_FAILED
        assert FetchStatus.SUCCESS_ZERO.value != FetchStatus.CONNECTION_FAILED.value

    def test_success_data_differs_from_success_zero(self):
        """SUCCESS_DATA (returned records) ≠ SUCCESS_ZERO (returned none)."""
        assert FetchStatus.SUCCESS_DATA != FetchStatus.SUCCESS_ZERO


# ---------------------------------------------------------------------------
# FetchResult tests
# ---------------------------------------------------------------------------


class TestFetchResult:
    """FetchResult correctly classifies outcomes."""

    def test_success_data_is_success(self):
        result = FetchResult(status=FetchStatus.SUCCESS_DATA, items=[{"a": 1}])
        assert result.is_success
        assert not result.is_zero
        assert not result.is_failure

    def test_success_zero_is_success_and_zero(self):
        result = FetchResult(status=FetchStatus.SUCCESS_ZERO)
        assert result.is_success
        assert result.is_zero
        assert not result.is_failure

    def test_connection_failed_is_failure(self):
        result = FetchResult(
            status=FetchStatus.CONNECTION_FAILED,
            error_message="Connection refused",
        )
        assert not result.is_success
        assert not result.is_zero
        assert result.is_failure

    def test_http_client_error_is_failure(self):
        result = FetchResult(
            status=FetchStatus.HTTP_CLIENT_ERROR,
            error_code=404,
            error_message="Not found",
        )
        assert result.is_failure

    def test_parse_failed_is_failure(self):
        result = FetchResult(
            status=FetchStatus.PARSE_FAILED,
            error_message="Invalid JSON",
        )
        assert result.is_failure

    def test_success_data_never_empty_list_on_failure(self):
        """GOAL CRITERION 2: Failed fetch must have empty items, not fake data."""
        result = FetchResult(
            status=FetchStatus.CONNECTION_FAILED,
            error_message="Timeout",
        )
        assert result.items == [], "Failed fetch must have empty items list, not fake/mocked data"
        assert result.total_records == 0

    def test_evidence_state_mapping(self):
        """Each FetchStatus maps to a valid evidence_state."""
        for status in FetchStatus:
            state = FetchResult(status=status).evidence_state
            valid_states = {
                "success_with_data",
                "success_zero",
                "connection_failed",
                "parse_failed",
                "transform_failed",
                "persist_failed",
                "not_applicable",
                "not_investigated",
                "partial",
                "auth_failed",
            }
            assert state in valid_states, f"FetchStatus.{status.name} maps to '{state}', not in valid evidence states"


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------


class TestCrawlCheckpoint:
    """Reentrant checkpoint for backfill."""

    def test_fresh_checkpoint_empty(self):
        """New checkpoint has no completed windows."""
        cp = CrawlCheckpoint(mode="backfill_3y")
        assert cp.completed_windows == []
        assert cp.total_contracts_fetched == 0
        assert cp.total_windows_completed == 0

    def test_checkpoint_serialization_roundtrip(self):
        """Checkpoint survives to_dict → from_dict."""
        cp = CrawlCheckpoint(
            source="pncp_contracts",
            mode="backfill_3y",
            completed_windows=["20230701_20230731", "20230801_20230831"],
            total_contracts_fetched=150,
            total_windows_completed=2,
        )
        data = cp.to_dict()
        restored = CrawlCheckpoint.from_dict(data)

        assert restored.source == cp.source
        assert restored.mode == cp.mode
        assert restored.completed_windows == cp.completed_windows
        assert restored.total_contracts_fetched == cp.total_contracts_fetched
        assert restored.total_windows_completed == cp.total_windows_completed

    def test_save_and_load_checkpoint(self):
        """Checkpoint can be saved to disk and loaded back."""
        cp = CrawlCheckpoint(
            mode="backfill_3y",
            completed_windows=["20240101_20240131"],
            total_contracts_fetched=42,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "contracts_backfill_3y.json")
            with patch(
                "scripts.crawl.contracts_crawler._checkpoint_path",
                return_value=path,
            ):
                save_checkpoint(cp)
                assert os.path.exists(path)

                loaded = load_checkpoint("backfill_3y")
                assert loaded.completed_windows == ["20240101_20240131"]
                assert loaded.total_contracts_fetched == 42

    def test_load_corrupt_checkpoint_returns_fresh(self):
        """Corrupt checkpoint file returns a fresh CrawlCheckpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "contracts_backfill_3y.json")
            with open(path, "w") as f:
                f.write("not valid json {{{")

            with patch(
                "scripts.crawl.contracts_crawler._checkpoint_path",
                return_value=path,
            ):
                loaded = load_checkpoint("backfill_3y")
                assert loaded.completed_windows == []
                assert loaded.total_contracts_fetched == 0

    def test_load_missing_checkpoint_returns_fresh(self):
        """Missing checkpoint file returns a fresh CrawlCheckpoint."""
        loaded = load_checkpoint("nonexistent_mode")
        assert loaded.completed_windows == []
        assert loaded.mode == "nonexistent_mode"


# ---------------------------------------------------------------------------
# UF not defaulted to SC tests
# ---------------------------------------------------------------------------


class TestUfNotDefaulted:
    """GOAL CRITERION 2: UF is never presumed 'SC'."""

    def test_uf_from_api_used_primarily(self):
        """When API provides ufSigla, it must be used."""
        rec = {
            "numeroControlePNCP": "TEST123",
            "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Test"},
            "unidadeOrgao": {"ufSigla": "PR", "municipioNome": "Curitiba"},
            "niFornecedor": "00999999000199",
            "nomeRazaoSocialFornecedor": "Fornecedor X",
            "objetoContrato": "Teste",
            "valorGlobal": 1000.0,
            "dataAssinatura": "2025-01-01T00:00:00Z",
        }
        result = _transform_record(rec)
        assert result is not None
        assert result["uf"] == "PR", f"UF should be 'PR' from API, got '{result['uf']}'"

    def test_uf_from_cnpj_lookup_used_secondary(self):
        """When API has no ufSigla, CNPJ root lookup is used."""
        rec = {
            "numeroControlePNCP": "TEST456",
            "orgaoEntidade": {"cnpj": "00000000000123", "razaoSocial": "Federal"},
            "unidadeOrgao": {},
            "niFornecedor": "00999999000199",
            "nomeRazaoSocialFornecedor": "Fornecedor Y",
            "objetoContrato": "Teste",
            "valorGlobal": 2000.0,
            "dataAssinatura": "2025-01-01T00:00:00Z",
        }
        result = _transform_record(rec)
        assert result is not None
        assert result["uf"] == "DF", f"UF should be 'DF' from CNPJ root (000000), got '{result['uf']}'"

    def test_uf_never_defaults_to_sc(self):
        """When both API and CNPJ lookup fail, UF stays None — NEVER 'SC'."""
        rec = {
            "numeroControlePNCP": "TEST789",
            "orgaoEntidade": {"cnpj": "99222222000123", "razaoSocial": "Unknown"},
            "unidadeOrgao": {},  # No ufSigla
            "niFornecedor": "00999999000199",
            "nomeRazaoSocialFornecedor": "Fornecedor Z",
            "objetoContrato": "Teste",
            "valorGlobal": 3000.0,
            "dataAssinatura": "2025-01-01T00:00:00Z",
        }
        result = _transform_record(rec)
        assert result is not None
        assert result["uf"] is None, (
            f"UF must be None when both API and CNPJ lookup fail. Got: '{result['uf']}'. DO NOT default to 'SC'."
        )

    def test_uf_empty_string_treated_as_missing(self):
        """Empty ufSigla string is treated as missing."""
        rec = {
            "numeroControlePNCP": "TEST000",
            "orgaoEntidade": {"cnpj": "99222222000123", "razaoSocial": "Unknown"},
            "unidadeOrgao": {"ufSigla": ""},  # Empty string
            "niFornecedor": "00999999000199",
            "nomeRazaoSocialFornecedor": "Fornecedor W",
            "objetoContrato": "Teste",
            "valorGlobal": 4000.0,
        }
        result = _transform_record(rec)
        assert result is not None
        assert result["uf"] is None, f"Empty '' ufSigla must result in None UF, got '{result['uf']}'"


# ---------------------------------------------------------------------------
# _fetch_page mock tests (offline — mock urllib)
# ---------------------------------------------------------------------------


class TestFetchPageMocked:
    """Test _fetch_page with mocked urllib to verify error discrimination."""

    @patch("urllib.request.urlopen")
    def test_fetch_page_success_with_data(self, mock_urlopen):
        """Successful fetch with data returns SUCCESS_DATA."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {
                "data": [{"numeroControlePNCP": "X"}],
                "totalRegistros": 1,
                "totalPaginas": 1,
            }
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = _fetch_page("20250101", "20250131", 1)
        assert result.status == FetchStatus.SUCCESS_DATA
        assert len(result.items) == 1
        assert result.is_success

    @patch("urllib.request.urlopen")
    def test_fetch_page_success_zero(self, mock_urlopen):
        """Successful fetch with zero items returns SUCCESS_ZERO."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {
                "data": [],
                "totalRegistros": 0,
                "totalPaginas": 1,
            }
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = _fetch_page("20250101", "20250131", 1)
        assert result.status == FetchStatus.SUCCESS_ZERO
        assert result.is_zero
        assert result.is_success  # Still success, just empty

    @patch("urllib.request.urlopen")
    def test_fetch_page_parse_failure(self, mock_urlopen):
        """Invalid JSON returns PARSE_FAILED, not empty list."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json at all {{{"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = _fetch_page("20250101", "20250131", 1)
        assert result.status == FetchStatus.PARSE_FAILED
        assert result.is_failure
        assert result.items == []

    @patch("urllib.request.urlopen")
    def test_fetch_page_http_404_returns_client_error(self, mock_urlopen):
        """HTTP 404 returns HTTP_CLIENT_ERROR, not empty success."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://test",
            404,
            "Not Found",
            {},
            None,
        )

        result = _fetch_page("20250101", "20250131", 1)
        assert result.status == FetchStatus.HTTP_CLIENT_ERROR
        assert result.is_failure
        assert result.error_code == 404

    @patch("urllib.request.urlopen")
    def test_fetch_page_connection_refused(self, mock_urlopen):
        """Connection refused returns CONNECTION_FAILED."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = _fetch_page("20250101", "20250131", 1)
        assert result.status == FetchStatus.CONNECTION_FAILED
        assert result.is_failure

    @patch("urllib.request.urlopen")
    def test_fetch_page_http_500_with_retries(self, mock_urlopen):
        """HTTP 500 with retries returns HTTP_SERVER_ERROR after exhausting."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://test",
            500,
            "Internal Server Error",
            {},
            None,
        )

        result = _fetch_page("20250101", "20250131", 1)
        # Should retry CONTRACTS_MAX_RETRIES times, then fail
        assert result.status == FetchStatus.HTTP_SERVER_ERROR
        assert result.is_failure
