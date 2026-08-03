"""Legacy decision mapping (ACCEPT/REJECT/DEFER → GO/REVIEW/NO_GO)."""

from __future__ import annotations

from scripts.decision_memory.models import HumanDecision, LegacyDecision, SystemRecommendation

# Canonical mapping for Extra review ledger. Original value is always preserved.
LEGACY_TO_HUMAN: dict[str, HumanDecision] = {
    "ACCEPT": HumanDecision.GO,
    "DEFER": HumanDecision.REVIEW,
    "REJECT": HumanDecision.NO_GO,
}

HUMAN_TO_LEGACY: dict[HumanDecision, LegacyDecision] = {
    HumanDecision.GO: LegacyDecision.ACCEPT,
    HumanDecision.REVIEW: LegacyDecision.DEFER,
    HumanDecision.NO_GO: LegacyDecision.REJECT,
}


class MappingAmbiguousError(ValueError):
    """Raised when a legacy value cannot be mapped without silent conversion."""


def map_legacy_decision(value: str | None) -> tuple[HumanDecision, LegacyDecision]:
    """Map legacy decision string to canonical human decision.

    Returns (canonical, original_as_enum). Never invents ACCEPT/REJECT/DEFER.
    """
    if value is None or not str(value).strip():
        raise MappingAmbiguousError("legacy decision missing; refuse silent default")
    raw = str(value).strip().upper()
    if raw in LEGACY_TO_HUMAN:
        return LEGACY_TO_HUMAN[raw], LegacyDecision(raw)
    # Already-canonical values accepted explicitly
    if raw in {d.value for d in HumanDecision}:
        human = HumanDecision(raw)
        return human, HUMAN_TO_LEGACY[human]
    raise MappingAmbiguousError(f"unmapped legacy decision {value!r}; requires human review, not silent conversion")


def map_system_recommendation(value: str | None) -> SystemRecommendation:
    if value is None or not str(value).strip():
        return SystemRecommendation.NOT_PROVIDED
    raw = str(value).strip().upper()
    # Common shortlist states that are not decisions
    aliases = {
        "ACCEPT": SystemRecommendation.GO,
        "REVIEW": SystemRecommendation.REVIEW,
        "REVIEW_REQUIRED": SystemRecommendation.REVIEW,
        "REJECT": SystemRecommendation.NO_GO,
        "NO_GO": SystemRecommendation.NO_GO,
        "GO": SystemRecommendation.GO,
        "UNKNOWN": SystemRecommendation.UNKNOWN,
        "ACTIONABLE": SystemRecommendation.REVIEW,
    }
    if raw in aliases:
        return aliases[raw]
    try:
        return SystemRecommendation(raw)
    except ValueError:
        return SystemRecommendation.UNKNOWN
