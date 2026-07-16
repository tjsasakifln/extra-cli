"""Tests for watermark_sync module."""
from __future__ import annotations

from scripts.crawl.watermark_sync import watermark_commit, watermark_read


class TestWatermarkSync:
    """Unit tests for watermark_sync wrapper functions."""

    def test_watermark_read_returns_value_or_none(self):
        """watermark_read returns a value or None — never crashes."""
        result = watermark_read(source="test", scope_key="page")
        # Should not raise; value can be None, str, or int (DB default)
        assert result is None or isinstance(result, (str, int))

    def test_watermark_commit_returns_bool(self):
        """watermark_commit returns True when DB is available, False when not."""
        # Clean up any previous test watermark
        result = watermark_commit(source="test", scope_key="page", value="0")
        assert isinstance(result, bool)
