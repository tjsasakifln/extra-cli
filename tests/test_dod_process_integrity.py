"""DoD §1 process integrity policy tests."""
from __future__ import annotations

from scripts.ops.dod_process_integrity import (
    POLICY,
    audit_dod_file,
    parse_completed_without_evidence,
)


def test_policy_flags() -> None:
    assert POLICY["code_without_execution_is_not_done"] is True
    assert POLICY["unit_test_is_not_e2e"] is True
    assert POLICY["checkbox_requires_evidence"] is True


def test_parse_detects_checked_without_evidence() -> None:
    sample = """
- [x] Algo feito sem prova.
- [x] Algo com evidência: scripts/ops/x.py + QA PASS.
- [ ] Ainda aberto.
"""
    weak = parse_completed_without_evidence(sample)
    assert any("sem prova" in w["text"] for w in weak)
    assert not any("com evidência" in w["text"].lower() for w in weak)


def test_audit_dod_runs_on_repo() -> None:
    report = audit_dod_file("DOD.md")
    assert report["checked"] > 0
    assert report["open"] > 0
    assert "rules" in report


def test_project_done_requires_three_rolls() -> None:
    from scripts.ops.dod_process_integrity import PROJECT_DONE_ROLLS, project_done_allowed

    assert len(PROJECT_DONE_ROLLS) == 3
    blocked = project_done_allowed(
        current_stage_complete=True,
        post_vps_complete=False,
        infra_independent_complete=True,
    )
    assert blocked["allowed"] is False
    assert "post_vps_requirements" in blocked["missing"]
    ok = project_done_allowed(
        current_stage_complete=True,
        post_vps_complete=True,
        infra_independent_complete=True,
    )
    assert ok["allowed"] is True
