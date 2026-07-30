"""Publishability gates for public-agency leads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.public_agency.conflict import STATE_BLOCKED, STATE_CLEARED, ConflictAssessment, blocks_outreach
from scripts.public_agency.signals import SignalHit, material_need_signals

PUBLISHABLE = "PUBLISHABLE"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
RESEARCH_REQUIRED = "RESEARCH_REQUIRED"
COMPLIANCE_BLOCKED = "COMPLIANCE_BLOCKED"
CONFLICT_BLOCKED = "CONFLICT_BLOCKED"
NOT_A_FIT = "NOT_A_FIT"


@dataclass
class PublishabilityResult:
    category: str
    reasons: list[str] = field(default_factory=list)
    publishable: bool = False
    relationship_state: str = "IDENTIFIED"
    checks: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_publishability(
    *,
    has_official_identity: bool,
    signals: list[SignalHit],
    has_official_evidence: bool,
    service_fit_score: float,
    explanation: str | None,
    conflict: ConflictAssessment,
    compliance_blocks: list[str] | None = None,
    has_institutional_contact: bool = False,
    contact_research_justified: bool = False,
    min_service_fit: float = 0.35,
) -> PublishabilityResult:
    compliance_blocks = list(compliance_blocks or [])
    reasons: list[str] = []
    checks = {
        "official_identity": has_official_identity,
        "material_need_signal": bool(material_need_signals(signals)),
        "official_evidence": has_official_evidence,
        "service_fit": service_fit_score >= min_service_fit,
        "legible_explanation": bool(explanation and explanation.strip()),
        "no_conflict_block": conflict.state != STATE_BLOCKED,
        "no_critical_compliance_block": not compliance_blocks,
        "institutional_contact_or_research": has_institutional_contact or contact_research_justified,
    }

    if conflict.state == STATE_BLOCKED:
        return PublishabilityResult(
            category=CONFLICT_BLOCKED,
            reasons=["conflict_blocked"] + conflict.reasons,
            publishable=False,
            relationship_state="CONFLICT_BLOCKED",
            checks=checks,
        )

    if compliance_blocks:
        return PublishabilityResult(
            category=COMPLIANCE_BLOCKED,
            reasons=compliance_blocks,
            publishable=False,
            relationship_state="DISQUALIFIED",
            checks=checks,
        )

    if not has_official_identity:
        return PublishabilityResult(
            category=RESEARCH_REQUIRED,
            reasons=["missing_official_identity"],
            publishable=False,
            relationship_state="RESEARCHED",
            checks=checks,
        )

    if not checks["material_need_signal"]:
        # Small municipality alone is NOT enough
        if any(s.signal_id == "small_municipality" and s.status == "FIRED" for s in signals):
            reasons.append("small_municipality_alone_not_sufficient")
        reasons.append("no_material_need_signal")
        return PublishabilityResult(
            category=NOT_A_FIT if not has_official_evidence else RESEARCH_REQUIRED,
            reasons=reasons,
            publishable=False,
            relationship_state="RESEARCHED",
            checks=checks,
        )

    if not has_official_evidence:
        return PublishabilityResult(
            category=RESEARCH_REQUIRED,
            reasons=["no_official_evidence"],
            publishable=False,
            relationship_state="RESEARCHED",
            checks=checks,
        )

    if service_fit_score < min_service_fit:
        return PublishabilityResult(
            category=NOT_A_FIT,
            reasons=["service_fit_below_threshold"],
            publishable=False,
            relationship_state="DISQUALIFIED",
            checks=checks,
        )

    if not checks["legible_explanation"]:
        return PublishabilityResult(
            category=REVIEW_REQUIRED,
            reasons=["missing_explanation"],
            publishable=False,
            relationship_state="HUMAN_REVIEW_REQUIRED",
            checks=checks,
        )

    if not checks["institutional_contact_or_research"]:
        return PublishabilityResult(
            category=RESEARCH_REQUIRED,
            reasons=["no_institutional_contact"],
            publishable=False,
            relationship_state="RESEARCHED",
            checks=checks,
        )

    # Conflict still pending → can be publishable for human review queue but not outreach
    if blocks_outreach(conflict) and conflict.state != STATE_CLEARED:
        return PublishabilityResult(
            category=PUBLISHABLE if all(
                checks[k]
                for k in (
                    "official_identity",
                    "material_need_signal",
                    "official_evidence",
                    "service_fit",
                    "legible_explanation",
                )
            )
            else REVIEW_REQUIRED,
            reasons=["conflict_human_review_required_before_outreach"],
            publishable=True,  # publishable for Tiago review queue
            relationship_state="HUMAN_REVIEW_REQUIRED",
            checks=checks,
        )

    return PublishabilityResult(
        category=PUBLISHABLE,
        reasons=["all_minimum_gates_passed"],
        publishable=True,
        relationship_state="HUMAN_REVIEW_REQUIRED",
        checks=checks,
    )
