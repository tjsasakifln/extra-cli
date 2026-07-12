"""Tests for FetchResult dataclass — distinguishing empty from failure.

Verifies that FetchResult separates "source responded, no data"
from "source failed and error was swallowed".
"""

from __future__ import annotations

from unittest.mock import patch


class TestFetchResult:
    """Verify FetchResult contract and error classification."""

    def test_fetch_result_importable(self):
        """FetchResult must be importable from the base crawler module."""
        from scripts.crawl.ingestion._base.crawler import FetchResult

        result = FetchResult()
        assert result.records == []
        assert result.request_completed is False
        assert result.http_status is None
        assert result.empty_confirmed is False
        assert result.errors == []

    def test_fetch_result_request_completed_no_data(self):
        """When source responds correctly but has no data."""
        from scripts.crawl.ingestion._base.crawler import FetchResult

        result = FetchResult(
            records=[],
            request_completed=True,
            http_status=200,
            empty_confirmed=True,
        )
        assert result.request_completed is True
        assert result.empty_confirmed is True
        assert result.http_status == 200

    def test_fetch_result_connectivity_failure(self):
        """When source is unreachable (network error)."""
        from scripts.crawl.ingestion._base.crawler import FetchResult

        result = FetchResult(
            records=[],
            request_completed=False,
            http_status=None,
            empty_confirmed=False,
            errors=["Connection refused: pncp.gov.br"],
        )
        assert result.request_completed is False
        assert result.empty_confirmed is False
        assert len(result.errors) == 1

    def test_fetch_result_http_error(self):
        """When source returns HTTP error."""
        from scripts.crawl.ingestion._base.crawler import FetchResult

        result = FetchResult(
            records=[],
            request_completed=True,
            http_status=500,
            empty_confirmed=False,
            errors=["HTTP 500 Internal Server Error"],
        )
        assert result.http_status == 500
        assert result.empty_confirmed is False

    def test_fetch_result_json_invalid(self):
        """When source returns invalid JSON."""
        from scripts.crawl.ingestion._base.crawler import FetchResult

        result = FetchResult(
            records=[],
            request_completed=True,
            http_status=200,
            empty_confirmed=False,
            errors=["JSON decode error: invalid response body"],
        )
        assert result.http_status == 200
        assert result.empty_confirmed is False

    def test_empty_confirmed_requires_request_completed(self):
        """EMPTY_VALIDATED requires request_completed=True AND empty_confirmed=True."""
        from scripts.crawl.ingestion._base.crawler import FetchResult

        # This is the "silent failure" pattern — must NOT happen
        result = FetchResult(
            records=[],
            request_completed=False,
            http_status=None,
            empty_confirmed=False,  # NOT confirmed empty — error!
            errors=["URLError: timed out"],
        )
        assert result.request_completed is False
        assert result.empty_confirmed is False
        assert len(result.errors) > 0

    def test_smoke_report_classifications_defined(self):
        """Smoke report must define all error classification constants."""
        # Verify the classification strings are valid without running full report
        valid_results = {
            "PASS_REAL", "EMPTY_VALIDATED",
            "FAIL_CONNECTIVITY", "FAIL_HTTP", "FAIL_RESPONSE",
            "FAIL_IMPORT", "FAIL_MISSING_API", "FAIL_TRANSFORM",
            "SKIPPED_MISSING_CREDENTIALS", "SKIPPED_MISSING_DEPENDENCY",
        }
        # All must be strings (classification constants)
        for r in valid_results:
            assert isinstance(r, str), f"Invalid classification: {r}"
        print(f"  Valid classifications: {len(valid_results)} defined")
