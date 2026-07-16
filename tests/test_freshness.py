"""Tests for freshness evaluator module."""
from __future__ import annotations

from scripts.crawl.freshness import FRESHNESS_ORDER, SourceFreshness


class TestSourceFreshness:
    """Unit tests for SourceFreshness data class."""

    def test_to_dict_contains_keys(self):
        sf = SourceFreshness(source="test", level="fresh")
        d = sf.to_dict()
        assert d["source"] == "test"
        assert d["level"] == "fresh"
        assert "coverage_pct" in d

    def test_level_order(self):
        assert FRESHNESS_ORDER["fresh"] < FRESHNESS_ORDER["stale"]
        assert FRESHNESS_ORDER["stale"] < FRESHNESS_ORDER["unknown"]
        assert FRESHNESS_ORDER["unknown"] < FRESHNESS_ORDER["never_crawled"]

    def test_default_values(self):
        sf = SourceFreshness(source="test")
        assert sf.level == "unknown"
        assert sf.coverage_pct == 0.0
        assert sf.sla_hours == 48  # DEFAULT_SLA_HOURS
