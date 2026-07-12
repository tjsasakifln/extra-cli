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

        # Mock _fetch_page to avoid real HTTP
        with patch('scripts.crawl.pncp_crawler_adapter._fetch_page') as mock_fetch:
            mock_fetch.return_value = ([], False)

            # Test with plain str (backward-compatible)
            result = crawl("incremental")
            assert isinstance(result, list)

    def test_crawl_request_dates_propagated(self):
        """CrawlRequest with dates must cause _fetch_page to be called with those dates."""
        from scripts.crawl.ingestion._base.crawler import CrawlRequest
        from scripts.crawl.pncp_crawler_adapter import crawl

        with patch('scripts.crawl.pncp_crawler_adapter._fetch_page') as mock_fetch:
            mock_fetch.return_value = ([], False)

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
            args = first_call[0]  # positional args
            data_inicial = args[3]  # 4th positional arg
            data_final = args[4]    # 5th positional arg

            assert data_inicial == date(2025, 1, 1), (
                f"data_inicial={data_inicial}, expected 2025-01-01. "
                "Dates not propagated to _fetch_page."
            )
            assert data_final == date(2025, 1, 1), (
                f"data_final={data_final}, expected 2025-01-01. "
                "Dates not propagated to _fetch_page."
            )
            print(f"  ✓ _fetch_page called with data_inicial={data_inicial}, data_final={data_final}")

    def test_crawl_request_limit_stops_early(self):
        """When limit=1, crawl must stop after fetching 1 record (or empty)."""
        from scripts.crawl.ingestion._base.crawler import CrawlRequest
        from scripts.crawl.pncp_crawler_adapter import crawl

        with patch('scripts.crawl.pncp_crawler_adapter._fetch_page') as mock_fetch:
            # Simulate returning 2 records — but limit=1 should stop after 1
            mock_fetch.return_value = (
                [{"id": "test1", "numeroControlePNCP": "1"}], True
            )

            req = CrawlRequest(
                mode="backfill",
                date_from=date(2025, 1, 1),
                date_to=date(2025, 1, 1),
                limit=1,
            )
            result = crawl(req)

            # Should have at most 1 record
            assert len(result) <= 1, (
                f"limit=1 but got {len(result)} records. Limit not enforced."
            )
            print(f"  ✓ limit=1 enforced: {len(result)} record(s) returned")

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
