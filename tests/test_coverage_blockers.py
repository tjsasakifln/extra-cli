"""Tests for coverage blockers — Story 1.5.

Tests cover:
    - CoverageBlocker creation
    - get_blockers_for_source returns known blockers
    - get_all_known_blockers returns all
    - check_missing_credentials_blocker
"""

from __future__ import annotations

from scripts.coverage.blockers import (
    CoverageBlocker,
    check_missing_credentials_blocker,
    get_all_known_blockers,
    get_blockers_for_source,
)


class TestCoverageBlocker:
    def test_default_values(self):
        blocker = CoverageBlocker(source="pncp")
        assert blocker.source == "pncp"
        assert blocker.entity == "ALL"
        assert blocker.capability == "open_tenders"
        assert blocker.action_required == ""
        assert blocker.owner == "TBD"

    def test_custom_values(self):
        blocker = CoverageBlocker(
            source="dom_sc",
            entity="ALL",
            capability="open_tenders",
            action_required="Get API key",
            recommended_action="Contact CIGA",
            owner="Operations",
            impact="Missing municipal bids",
        )
        assert blocker.source == "dom_sc"
        assert blocker.action_required == "Get API key"
        assert blocker.owner == "Operations"

    def test_to_dict(self):
        blocker = CoverageBlocker(source="test", action_required="fix")
        d = blocker.to_dict()
        assert d["source"] == "test"
        assert d["action_required"] == "fix"
        assert "created_at" in d


class TestGetBlockersForSource:
    def test_pncp_blockers(self):
        blockers = get_blockers_for_source("pncp")
        assert len(blockers) >= 1
        assert any("PNCP v3" in b.action_required for b in blockers)

    def test_dom_sc_blockers(self):
        blockers = get_blockers_for_source("dom_sc")
        assert len(blockers) >= 1
        assert any("CIGA" in b.recommended_action for b in blockers)

    def test_unknown_source(self):
        blockers = get_blockers_for_source("nonexistent_source")
        assert len(blockers) == 0


class TestGetAllKnownBlockers:
    def test_returns_all(self):
        blockers = get_all_known_blockers()
        # Should have at least pncp, dom_sc, doe_sc, tce_sc, mides_bigquery
        assert len(blockers) >= 5

    def test_all_have_sources(self):
        blockers = get_all_known_blockers()
        sources = {b.source for b in blockers}
        assert "pncp" in sources
        assert "dom_sc" in sources
        assert "tce_sc" in sources
        assert "mides_bigquery" in sources


class TestCheckMissingCredentials:
    def test_no_missing_returns_none(self):
        blocker = check_missing_credentials_blocker("pncp", [])
        assert blocker is None

    def test_missing_creates_blocker(self):
        blocker = check_missing_credentials_blocker("dom_sc", ["DOM_SC_API_KEY"])
        assert blocker is not None
        assert blocker.blocker_type == "credential"
        assert "DOM_SC_API_KEY" in blocker.action_required
        assert blocker.source == "dom_sc"

    def test_multiple_missing(self):
        blocker = check_missing_credentials_blocker(
            "doe_sc", ["DOE_SC_LOGIN", "DOE_SC_PASSWORD"]
        )
        assert blocker is not None
        assert "DOE_SC_LOGIN" in blocker.action_required
        assert "DOE_SC_PASSWORD" in blocker.action_required
