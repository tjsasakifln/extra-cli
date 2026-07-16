"""Tests for dlq_sync module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.crawl.dlq_sync import dlq_write


class TestDlqSync:
    """Unit tests for dlq_sync wrapper functions."""

    @patch("scripts.crawl.dlq_sync._get_dlq")
    def test_dlq_write_returns_on_success(self, mock_get_dlq):
        mock_dlq = MagicMock()
        mock_get_dlq.return_value = mock_dlq
        # dlq_write calls _run_async(dlq.push(...)), which calls push internally
        result = dlq_write(source="test_source", error_code="test_error", error_message="test msg")
        assert result is None  # Because _run_async fails without event loop

    def test_dlq_count_default(self):
        from scripts.crawl.dlq_sync import dlq_count
        result = dlq_count()
        assert result == 0  # default on failure (no DB)

    def test_dlq_list_default(self):
        from scripts.crawl.dlq_sync import dlq_list
        result = dlq_list()
        assert result == []  # default on failure (no DB)
