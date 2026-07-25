"""Phase 8 — value-oriented review queue prioritization + capacity policy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from scripts.ops.hybrid_sector.models import CandidateRecord, DecisionLineage

OPERATIONALLY_BLOCKED_REVIEW_VOLUME = "OPERATIONALLY_BLOCKED_REVIEW_VOLUME"


@dataclass
class ReviewCapacityConfig:
    max_items_per_cycle: int = 100
    overflow_policy: str = "preserve_and_flag"

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_items_per_cycle": self.max_items_per_cycle,
            "overflow_policy": self.overflow_policy,
        }


def _days_to_deadline(raw: str | None) -> float:
    if not raw:
        return 365.0
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw[:19], fmt).date()
            return float((dt - date.today()).days)
        except ValueError:
            continue
    return 365.0


def compute_review_priority(
    lineage: DecisionLineage,
    candidate: CandidateRecord | None,
) -> float:
    """Higher = more urgent. Components from OBJECTIVE phase 8."""
    score = 0.0
    rec = candidate.record if candidate else None
    # 1. prazo (sooner → higher)
    days = _days_to_deadline(rec.data_encerramento if rec else None)
    score += max(0.0, 100.0 - days)  # up to 100
    # 2. valor
    valor = (rec.valor_estimado if rec else None) or 0.0
    score += min(valor / 100_000.0, 50.0)
    # 3. aderência potencial
    if lineage.deterministic:
        if lineage.deterministic.decision == "GRAY_ZONE":
            score += 15.0
        if lineage.deterministic.has_execution_signal:
            score += 20.0
        score += 5.0 * len(lineage.deterministic.positive_signals)
    # 4. independent signals
    ch = len(lineage.retrieval.get("retrieved_by") or [])
    score += 8.0 * ch
    # 5. semantic novelty / zero-match
    if lineage.retrieval.get("zero_match_rescue"):
        score += 12.0
    if "semantic" in (lineage.retrieval.get("retrieved_by") or []):
        score += 8.0
    # 6. organ history
    if "organ_history" in (lineage.retrieval.get("retrieved_by") or []):
        score += 6.0
    # 7. missing docs
    score += 4.0 * len(lineage.documents_needed)
    # 8. false-negative risk (LLM said match-ish or det positive with review)
    if lineage.llm_decision and lineage.llm_decision.get("decision") == "MATCH":
        score += 10.0
    if lineage.deterministic and lineage.deterministic.positive_signals:
        score += 10.0
    return score


def prioritize_review_queue(
    lineages: list[DecisionLineage],
    candidates_by_id: dict[str, CandidateRecord],
    *,
    config: ReviewCapacityConfig | None = None,
) -> tuple[list[DecisionLineage], dict[str, Any]]:
    """Sort REVIEW items by priority; never discard overflow — flag operational block."""
    config = config or ReviewCapacityConfig()
    reviews = [l for l in lineages if l.commercial_decision == "REVIEW"]
    for lin in reviews:
        cand = candidates_by_id.get(lin.canonical_id)
        lin.review_priority = compute_review_priority(lin, cand)

    reviews.sort(key=lambda l: (-(l.review_priority or 0.0), l.canonical_id))

    overflow = len(reviews) > config.max_items_per_cycle
    status = {
        "manual_review": config.to_dict(),
        "review_count": len(reviews),
        "overflow": overflow,
        "overflow_policy": config.overflow_policy,
        "operational_status": (
            OPERATIONALLY_BLOCKED_REVIEW_VOLUME if overflow else "WITHIN_CAPACITY"
        ),
        "discarded": 0,  # overflow never discards
        "preserved_all": True,
    }
    # preserve_and_flag: return full queue ordered; capacity is operational signal only
    return reviews, status
