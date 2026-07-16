"""Tests for provenance_sync module."""
from __future__ import annotations

from scripts.crawl.provenance_sync import provenance_complete, provenance_fail, provenance_start


class TestProvenanceSync:
    """Unit tests for provenance_sync wrapper functions."""

    def test_provenance_start_never_crashes(self):
        """provenance_start returns a string or None — never crashes."""
        run_id = provenance_start(source="test", mode="full")
        assert run_id is None or isinstance(run_id, str)

    def test_provenance_complete_never_crashes(self):
        """provenance_complete returns True or False — never crashes."""
        result = provenance_complete(run_id="test-run", source="test")
        assert isinstance(result, bool)

    def test_provenance_fail_never_crashes(self):
        """provenance_fail returns True or False — never crashes."""
        result = provenance_fail(run_id="test-run", source="test", error_message="oops")
        assert isinstance(result, bool)
