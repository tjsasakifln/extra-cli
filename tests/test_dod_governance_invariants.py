"""Governance invariants for low-hanging DOD family A."""
from __future__ import annotations

from scripts.ops import dod_process_integrity as dpi
from scripts.ops import requirement_states as rs


def test_policy_code_without_execution_not_done() -> None:
    assert dpi.POLICY["code_without_execution_is_not_done"] is True


def test_policy_unit_not_e2e() -> None:
    assert dpi.POLICY["unit_test_is_not_e2e"] is True


def test_policy_checkbox_requires_evidence() -> None:
    assert dpi.POLICY["checkbox_requires_evidence"] is True


def test_partial_never_gate_accepted() -> None:
    rec = rs.make_partial("i", "t", "half")
    assert rec.is_gate_accepted() is False
    assert rec.dod_checkbox == "[ ]"


def test_partial_checked_is_invalid() -> None:
    rec = rs.RequirementRecord(item_id="i", title="t", state="PARTIAL", dod_checkbox="[x]")
    assert rs.validate_record(rec)


def test_blocked_requires_fields_and_stays_visible() -> None:
    rec = rs.make_blocked("b", "t", owner="ops", cause="ext", next_test="retry")
    assert rec.state == "BLOCKED"
    assert rec.is_gate_accepted() is False


def test_not_applicable_requires_basis() -> None:
    rec = rs.make_not_applicable(
        "na",
        "t",
        basis="conditional_wording",
        justification="conditional wording in DOD",
        date="2026-07-29",
        evidence=["docs/ops/dod-convergence.md"],
    )
    assert rec.is_gate_accepted() is True


def test_field_absence_never_done_zero() -> None:
    assert "SOURCE_UNAVAILABLE" in rs.FIELD_ABSENCE_STATES
    assert "NOT_READY" in rs.FIELD_ABSENCE_STATES
    assert rs.RequirementState.DONE not in rs.FIELD_ABSENCE_STATES


def test_gate_only_done_and_na() -> None:
    assert rs.RequirementState.DONE in rs.GATE_ACCEPTED
    assert rs.RequirementState.NOT_APPLICABLE in rs.GATE_ACCEPTED
    assert rs.RequirementState.PARTIAL not in rs.GATE_ACCEPTED
    assert rs.RequirementState.OPEN not in rs.GATE_ACCEPTED
    assert rs.RequirementState.BLOCKED not in rs.GATE_ACCEPTED


def test_project_done_three_rolls() -> None:
    assert len(dpi.PROJECT_DONE_ROLLS) == 3
    all_ok = dpi.project_done_allowed(
        current_stage_complete=True,
        post_vps_complete=True,
        infra_independent_complete=True,
    )
    missing = dpi.project_done_allowed(
        current_stage_complete=True,
        post_vps_complete=False,
        infra_independent_complete=True,
    )
    assert all_ok["allowed"] is True
    assert missing["allowed"] is False


def test_reconstruct_available() -> None:
    assert callable(rs.reconstruct)
