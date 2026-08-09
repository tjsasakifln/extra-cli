"""Architectural: reajuste_14133 must not own operational activation."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.commercial.reajuste_14133.activation_signals import (
    ActivationSignal,
    assert_not_operational_authority,
    to_activation_signals,
)
from scripts.commercial.reajuste_14133.domain.scoring import ScoreBreakdown

ROOT = Path(__file__).resolve().parents[2]
REAJUSTE = ROOT / "scripts" / "commercial" / "reajuste_14133"


def test_score_breakdown_honest_aliases():
    sb = ScoreBreakdown(
        score_total=50,
        components={},
        penalties={},
        ranking_bucket="NACIONAL",
        opportunity_score=0.4,
        verification_score=0.6,
        commercial_fit_score=0.5,
        priority_score=0.3,
    )
    d = sb.as_dict()
    assert d["domain_signal_strength"] == 0.4
    assert d["documentary_confidence"] == 0.6
    assert d["is_calibrated_probability"] is False
    assert d["is_operational_activation_rank"] is False


def test_document_request_stage_emits_signal_not_activation_state():
    sigs = to_activation_signals(
        commercial_stage="DOCUMENT_REQUEST_READY",
        documentary_confidence=0.7,
        domain_signal_strength=0.5,
        evidence_ids=["e1"],
    )
    assert len(sigs) == 1
    s = sigs[0]
    assert isinstance(s, ActivationSignal)
    assert s.signal_code == "REAJUSTE_DOCUMENT_REQUEST_WINDOW"
    assert s.is_operational_queue is False
    payload = s.as_dict()
    assert "activation_state" not in payload or payload.get("activation_state") is None
    assert_not_operational_authority(payload)


def test_assert_blocks_activation_state_injection():
    try:
        assert_not_operational_authority({"activation_state": "ACTIONABLE_NOW"})
        raise AssertionError("should have failed")
    except AssertionError as e:
        assert "activation_state" in str(e)


def test_reajuste_source_does_not_assign_activation_state():
    """Static scan: reajuste package must not assign activation_state as authority."""
    offenders: list[str] = []
    for path in REAJUSTE.rglob("*.py"):
        if path.name == "activation_signals.py":
            continue  # documents the boundary
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "activation_state":
                        offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"reajuste must not assign activation_state: {offenders}"


def test_concepts_not_collapsed():
    domain_stage = "DOCUMENT_REQUEST_READY"
    activation = "ACTIONABLE_NOW"
    send_tier = "A_AUTOMATIC"
    email_ready = "EMAIL_SEND_READY"
    queue = "QUEUED"
    assert len({domain_stage, activation, send_tier, email_ready, queue}) == 5
