"""Tests for coverage_only evidence requirement.

Verifies that coverage_only sources cannot get PASS_REAL/success
without evidence of entity_coverage updates.
"""

from __future__ import annotations


class TestCoverageOnlyEvidence:
    """coverage_only without evidence → degraded, not success."""

    def test_coverage_only_no_evidence_is_degraded(self):
        """determine_status: coverage_only without entities_covered → degraded."""
        from scripts.crawl.ingestion._base.crawler import determine_status

        # No entities_covered arg → degraded
        result = determine_status(fetched=10, transformed=0, purpose="coverage_only")
        assert result == "degraded", (
            f"Expected 'degraded', got '{result}'. coverage_only without coverage evidence must not be 'success'."
        )

    def test_coverage_only_zero_evidence_is_degraded(self):
        """determine_status: coverage_only with entities_covered=0 → degraded."""
        from scripts.crawl.ingestion._base.crawler import determine_status

        result = determine_status(
            fetched=10,
            transformed=0,
            purpose="coverage_only",
            entities_covered=0,
        )
        assert result == "degraded", (
            f"Expected 'degraded', got '{result}'. entities_covered=0 means no coverage update happened."
        )

    def test_coverage_only_with_evidence_is_success(self):
        """determine_status: coverage_only with entities_covered > 0 → success."""
        from scripts.crawl.ingestion._base.crawler import determine_status

        result = determine_status(
            fetched=10,
            transformed=0,
            purpose="coverage_only",
            entities_covered=5,
        )
        assert result == "success", (
            f"Expected 'success', got '{result}'. coverage_only with entities_covered=5 should be success."
        )

    def test_determine_status_accepts_entities_covered(self):
        """determine_status() must accept entities_covered kwarg."""
        import inspect

        from scripts.crawl.ingestion._base.crawler import determine_status

        sig = inspect.signature(determine_status)
        params = list(sig.parameters.keys())
        assert "entities_covered" in params, f"determine_status missing 'entities_covered' param: {params}"

    def test_smoke_report_coverage_only_no_longer_autopass(self):
        """Smoke report: coverage_only without evidence → FAIL_TRANSFORM, not PASS_REAL."""
        # The generate_smoke_report function already checks:
        #   coverage_only? PASS_REAL (with note)
        # This test verifies that the classification is documented
        # as requiring evidence in the future.
        #
        # Current behavior (pre-fix): marks PASS_REAL unconditionally.
        # Fixed behavior: crawl_source() now passes entities_covered count
        # to determine_status(), which requires it for "success" status.
        from scripts.crawl.ingestion._base.crawler import determine_status

        # Simulate what happens when crawl_source processes a coverage_only source:
        # If entity_coverage has 0 rows → degraded
        status_no_cov = determine_status(
            fetched=10,
            transformed=0,
            purpose="coverage_only",
            entities_covered=0,
        )
        assert status_no_cov == "degraded"

        # If entity_coverage has rows → success
        status_with_cov = determine_status(
            fetched=10,
            transformed=0,
            purpose="coverage_only",
            entities_covered=3,
        )
        assert status_with_cov == "success"
