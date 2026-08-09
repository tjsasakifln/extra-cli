"""Bridge: reajuste domain stages → confenge_activation signal facts.

This module deliberately does NOT decide ACTIONABLE_NOW / WATCH / SUPPRESSED.
It only emits domain signals that confenge_activation may consume.

Architecture:
  reajuste_14133 domain stages
      ↓ to_activation_signals(...)
  confenge_activation planner (sole activation authority)
      ↓
  ACTIONABLE_NOW / WATCH / RESEARCH_REQUIRED / SUPPRESSED
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.commercial.reajuste_14133 import (
    CALCULABLE_ADJUSTMENT_CLAIM,
    DIAGNOSTIC_OUTREACH_READY,
    DOCUMENT_REQUEST_READY,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    POTENTIAL_ADJUSTMENT_SIGNAL,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)

# Signal codes consumable by confenge_activation (versioned strings).
SIGNAL_DOCUMENT_REQUEST_WINDOW = "REAJUSTE_DOCUMENT_REQUEST_WINDOW"
SIGNAL_DIAGNOSTIC_OUTREACH = "REAJUSTE_DIAGNOSTIC_OUTREACH"
SIGNAL_LIKELY_ADJUSTMENT = "REAJUSTE_LIKELY_ADJUSTMENT"
SIGNAL_VERIFIED_OPPORTUNITY = "REAJUSTE_VERIFIED_OPPORTUNITY"
SIGNAL_CALCULABLE_CLAIM = "REAJUSTE_CALCULABLE_CLAIM"
SIGNAL_POTENTIAL = "REAJUSTE_POTENTIAL_SIGNAL"

_STAGE_TO_SIGNAL = {
    DOCUMENT_REQUEST_READY: SIGNAL_DOCUMENT_REQUEST_WINDOW,
    DIAGNOSTIC_OUTREACH_READY: SIGNAL_DIAGNOSTIC_OUTREACH,
    LIKELY_ADJUSTMENT_OPPORTUNITY: SIGNAL_LIKELY_ADJUSTMENT,
    VERIFIED_ADJUSTMENT_OPPORTUNITY: SIGNAL_VERIFIED_OPPORTUNITY,
    CALCULABLE_ADJUSTMENT_CLAIM: SIGNAL_CALCULABLE_CLAIM,
    POTENTIAL_ADJUSTMENT_SIGNAL: SIGNAL_POTENTIAL,
}


@dataclass(frozen=True)
class ActivationSignal:
    """Domain fact for the activation planner — not a queue decision."""

    signal_code: str
    commercial_stage: str
    documentary_confidence: float
    claim_readiness: str
    evidence_ids: list[str] = field(default_factory=list)
    observed_at: str | None = None
    expires_at: str | None = None
    claims_to_avoid: list[str] = field(default_factory=list)
    domain_signal_strength: float = 0.0
    # Explicit non-authority markers
    is_operational_queue: bool = False
    is_calibrated_probability: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def to_activation_signals(
    *,
    commercial_stage: str,
    documentary_confidence: float = 0.0,
    domain_signal_strength: float = 0.0,
    evidence_ids: list[str] | None = None,
    observed_at: str | None = None,
    expires_at: str | None = None,
    claims_to_avoid: list[str] | None = None,
    claim_readiness: str = "",
) -> list[ActivationSignal]:
    """Map one commercial stage to zero or one activation signal fact."""
    stage = (commercial_stage or "").strip().upper()
    code = _STAGE_TO_SIGNAL.get(stage)
    if not code:
        return []
    return [
        ActivationSignal(
            signal_code=code,
            commercial_stage=stage,
            documentary_confidence=float(documentary_confidence or 0.0),
            claim_readiness=claim_readiness or stage,
            evidence_ids=list(evidence_ids or []),
            observed_at=observed_at,
            expires_at=expires_at,
            claims_to_avoid=list(claims_to_avoid or []),
            domain_signal_strength=float(domain_signal_strength or 0.0),
            is_operational_queue=False,
            is_calibrated_probability=False,
        )
    ]


def assert_not_operational_authority(payload: dict[str, Any]) -> None:
    """Hard guard: reajuste payloads must not claim activation authority."""
    if payload.get("is_operational_queue") is True:
        raise AssertionError("reajuste must not emit is_operational_queue=true")
    if payload.get("activation_state") in {
        "ACTIONABLE_NOW",
        "WATCH",
        "RESEARCH_REQUIRED",
        "SUPPRESSED",
    }:
        raise AssertionError(
            "reajuste must not set activation_state; confenge_activation owns that"
        )
