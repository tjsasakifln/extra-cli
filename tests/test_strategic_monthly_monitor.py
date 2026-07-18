"""Tests for strategic monthly monitoring cycle."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.ops.strategic_monthly_monitor import (
    audit_report,
    run_cycle,
    run_fixture_demo,
    fixture_snapshot_a,
    fixture_snapshot_b,
)


def test_two_cycle_fixture_proves_all_eight(tmp_path: Path) -> None:
    pkg = run_fixture_demo(tmp_path)
    aud = audit_report(pkg)
    assert aud["ok"] is True
    assert aud["summary"]["fail"] == 0
    assert pkg["proofs"]["new_editais_detected"] is True
    assert "SUSPENSAO" in pkg["proofs"]["status_events"]
    assert "REVOGACAO" in pkg["proofs"]["status_events"]
    assert "ALTERACAO_PRAZO" in pkg["proofs"]["status_events"]
    c2 = pkg["cycle_2"]
    assert c2["cycle"]["manual_diagnostic_rebuild_required"] is False
    assert c2["cycle"]["reused_previous_state"] is True
    assert c2["weekly_report"]["periodicity"] == "weekly"
    assert c2["monthly_report"]["periodicity"] == "monthly"
    assert c2["variation"]["has_previous"] is True
    # totals grow; "new_editais" metric is per-cycle delta count (may be same magnitude)
    assert c2["variation"]["fields"]["editais_total"]["delta"] >= 1
    assert c2["variation"]["fields"]["editais_total"]["current"] > c2["variation"]["fields"]["editais_total"]["previous"]


def test_first_cycle_no_previous_variation() -> None:
    as_of = date(2026, 7, 18)
    e, c = fixture_snapshot_a(as_of)
    report, state = run_cycle(editais=e, contracts=c, state=None, as_of=as_of)
    assert report.status == "OK"
    assert report.variation["has_previous"] is False
    assert state.last_edital_ids == ["ED-001", "ED-002"]
    # CT-001 in 90-180 window; CT-002 at +30 out
    assert len(report.expiring_contracts) == 1
    assert report.expiring_contracts[0]["contract_id"] == "CT-001"


def test_status_and_new_on_second_cycle() -> None:
    as_of = date(2026, 7, 18)
    e1, c1 = fixture_snapshot_a(as_of)
    _, s1 = run_cycle(editais=e1, contracts=c1, state=None, as_of=as_of)
    e2, c2 = fixture_snapshot_b(as_of)
    r2, _ = run_cycle(editais=e2, contracts=c2, state=s1, as_of=as_of)
    new_ids = {x["edital_id"] for x in r2.new_editais}
    assert "ED-003" in new_ids
    assert "ED-004" in new_ids  # not in previous snapshot
    events = {d["event_type"] for d in r2.status_deltas}
    assert "SUSPENSAO" in events
    assert r2.panorama["winners_count"] >= 2
