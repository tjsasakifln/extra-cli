"""Tests for honest commercial sample report."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.reports.commercial_sample_sc import build_report


def test_build_report_has_disclaimers_and_forbidden_claims():
    report = build_report(dsn=None)
    assert report["report"] == "commercial-sample-sc"
    assert report["confidence"] in {"low", "low_to_medium", "medium", "high"}
    assert isinstance(report["disclaimers"], list)
    assert len(report["disclaimers"]) >= 2
    forbidden = " ".join(report["claims_forbidden"]).lower()
    assert "90d" in forbidden or "3 anos" in forbidden or "3y" in forbidden or "backfill" in forbidden
    # Must not claim full pilot success in allowed claims when artifact is partial
    pilot = json.loads(Path("output/contracts/pilot-90d-next30d.json").read_text(encoding="utf-8"))
    if pilot.get("status") == "partial":
        assert report["contracts_pilot"]["status"] == "partial"
        assert report["contracts_pilot"]["go_no_go_3y"] == "NO-GO"


def test_db_unavailable_soft_fails():
    report = build_report(dsn=None)
    assert report["db_sample"]["available"] is False
