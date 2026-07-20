"""Adversarial absolute veto: model cannot ACCEPT over non-PASS verification."""
from __future__ import annotations

from scripts.cto.review_veto import (
    apply_absolute_veto,
    publication_forbidden,
    verification_blocks_accept,
)


def _review(verdict: str = "ACCEPT") -> dict:
    return {
        "schema_version": "1.0",
        "review_id": "rev-adv-1",
        "cycle_id": "cyc-adv",
        "decision_id": "dec-adv",
        "verdict": verdict,
        "summary": "model wants accept",
        "failed_criteria": [],
        "repair_instructions": [],
        "confidence": 0.99,
        "human_gate": {"required": False, "reason": None},
    }


def test_veto_accept_on_fail():
    out = apply_absolute_veto(_review("ACCEPT"), {"result": "FAIL", "criterion_matrix": []})
    assert out["verdict"] != "ACCEPT"
    assert out["verdict"] == "REPAIR"
    assert out["_veto"]["applied"] is True


def test_veto_accept_on_unsafe():
    out = apply_absolute_veto(_review("ACCEPT"), {"result": "UNSAFE", "criterion_matrix": []})
    assert out["verdict"] == "BLOCK"
    assert out["_veto"]["applied"] is True


def test_veto_accept_on_incomplete():
    out = apply_absolute_veto(_review("ACCEPT"), {"result": "INCOMPLETE"})
    assert out["verdict"] != "ACCEPT"


def test_veto_accept_on_unproven_matrix():
    verification = {
        "result": "PASS",  # mis-labeled aggregate
        "criterion_matrix": [{"criterion": "ac[0]", "status": "UNPROVEN"}],
    }
    assert verification_blocks_accept(verification) is True
    out = apply_absolute_veto(_review("ACCEPT"), verification)
    assert out["verdict"] != "ACCEPT"


def test_pass_allows_accept():
    out = apply_absolute_veto(
        _review("ACCEPT"),
        {"result": "PASS", "criterion_matrix": [{"status": "PASS"}]},
    )
    assert out["verdict"] == "ACCEPT"
    assert out["_veto"]["applied"] is False


def test_model_may_downgrade_pass_to_repair():
    out = apply_absolute_veto(
        _review("REPAIR"),
        {"result": "PASS", "criterion_matrix": []},
    )
    assert out["verdict"] == "REPAIR"


def test_publication_forbidden_without_accept():
    forbidden, reason = publication_forbidden(
        verification={"result": "PASS", "criterion_matrix": []},
        review=_review("REPAIR"),
    )
    assert forbidden is True
    assert "ACCEPT" in reason or "verdict" in reason


def test_publication_forbidden_on_fail_even_if_review_accept():
    review = apply_absolute_veto(_review("ACCEPT"), {"result": "FAIL"})
    forbidden, _ = publication_forbidden(
        verification={"result": "FAIL"},
        review=review,
    )
    assert forbidden is True
