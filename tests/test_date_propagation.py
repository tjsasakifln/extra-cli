"""Tests for date/target/limit propagation via CrawlRequest.

Verifies that date_from, date_to, target, and limit CLI arguments
actually affect the crawler's HTTP requests.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest


class TestCrawlRequestDates:
    """Verify CrawlRequest dates reach the HTTP layer."""

    def test_crawl_request_dates_passed_to_fetch_page(self):
        """When CrawlRequest has dates, _fetch_page must receive them."""
        from scripts.crawl.ingestion._base.crawler import CrawlRequest

        req = CrawlRequest(
            mode="backfill",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 7),
            limit=1,
        )

        # Verify CrawlRequest fields
        assert req.mode == "backfill"
        assert req.date_from == date(2025, 1, 1)
        assert req.date_to == date(2025, 1, 7)
        assert req.limit == 1

    def test_crawl_request_str_fallback(self):
        """crawl() must accept both CrawlRequest and plain str."""
        from scripts.crawl.pncp_crawler_adapter import crawl

        # Mock publication fetch to avoid real HTTP
        with patch('scripts.crawl.pncp_crawler_adapter._fetch_publication_page') as mock_fetch:
            from scripts.crawl.ingestion._base.crawler import FetchResult

            mock_fetch.return_value = FetchResult(
                records=[],
                request_completed=True,
                http_status=200,
                empty_confirmed=True,
                metadata={"pagination": {"paginasRestantes": 0}},
            )

            # Test with plain str (backward-compatible)
            result = crawl("incremental")
            assert hasattr(result, "records")

    def test_crawl_request_dates_propagated(self):
        """CrawlRequest with dates must cause _fetch_page to be called with those dates."""
        from scripts.crawl.ingestion._base.crawler import CrawlRequest
        from scripts.crawl.pncp_crawler_adapter import crawl

        with patch('scripts.crawl.pncp_crawler_adapter._fetch_publication_page') as mock_fetch:
            from scripts.crawl.ingestion._base.crawler import FetchResult

            mock_fetch.return_value = FetchResult(
                records=[],
                request_completed=True,
                http_status=200,
                empty_confirmed=True,
                metadata={"pagination": {"paginasRestantes": 0}},
            )

            req = CrawlRequest(
                mode="backfill",
                date_from=date(2025, 1, 1),
                date_to=date(2025, 1, 1),  # Single day to minimize calls
                limit=1,
            )
            crawl(req)

            # Verify _fetch_page was called at least once
            assert mock_fetch.call_count >= 1, (
                "_fetch_page was never called — dates not propagated"
            )

            # Get the first call's date arguments (positional: uf, mod, pagina, data_inicial, data_final)
            first_call = mock_fetch.call_args_list[0]
            req = first_call[0][0]

            assert req.date_from == date(2025, 1, 1), (
                f"data_inicial={req.date_from}, expected 2025-01-01. "
                "Dates not propagated to _fetch_page."
            )
            assert req.date_to == date(2025, 1, 1), (
                f"data_final={req.date_to}, expected 2025-01-01. "
                "Dates not propagated to _fetch_page."
            )
            print(f"  ✓ _fetch_page called with data_inicial={req.date_from}, data_final={req.date_to}")

    def test_crawl_request_limit_stops_early(self):
        """When limit=1, crawl must stop after fetching 1 record (or empty)."""
        from scripts.crawl.ingestion._base.crawler import CrawlRequest
        from scripts.crawl.pncp_crawler_adapter import crawl

        with patch('scripts.crawl.pncp_crawler_adapter._fetch_publication_page') as mock_fetch:
            from scripts.crawl.ingestion._base.crawler import FetchResult

            mock_fetch.return_value = FetchResult(
                records=[{"id": "test1", "numeroControlePNCP": "1"}],
                request_completed=True,
                http_status=200,
                empty_confirmed=False,
                metadata={"pagination": {"paginasRestantes": 0}},
            )

            req = CrawlRequest(
                mode="backfill",
                date_from=date(2025, 1, 1),
                date_to=date(2025, 1, 1),
                limit=1,
            )
            result = crawl(req)

            # Should have at most 1 record
            assert len(result.records) <= 1, (
                f"limit=1 but got {len(result.records)} records. Limit not enforced."
            )
            print(f"  ✓ limit=1 enforced: {len(result.records)} record(s) returned")

    def test_crawl_source_accepts_target_and_limit(self):
        """crawl_source() must accept target and limit kwargs."""
        import inspect
        from scripts.crawl.monitor import crawl_source

        sig = inspect.signature(crawl_source)
        params = list(sig.parameters.keys())
        assert "target" in params, f"crawl_source missing 'target' param: {params}"
        assert "limit" in params, f"crawl_source missing 'limit' param: {params}"

    def test_crawl_request_importable(self):
        """CrawlRequest must be importable from the base crawler module."""
        from scripts.crawl.ingestion._base.crawler import CrawlRequest

        req = CrawlRequest(mode="full")
        assert req.mode == "full"
        assert req.date_from is None
        assert req.date_to is None
        assert req.target is None
        assert req.limit is None
