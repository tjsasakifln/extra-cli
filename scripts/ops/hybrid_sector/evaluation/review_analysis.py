"""Review-rate triage by reason — reduce queue without arbitrary NO_MATCH inflation."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from scripts.ops.hybrid_sector.models import CandidateRecord, DecisionLineage

REVIEW_REASONS = (
    "short_text",
    "low_margin",
    "semantic_without_keyword",
    "zero_match",
    "mixed_scope",
    "insufficient_category",
    "llm_failure",
    "low_confidence",
    "divergence",
    "other",
)


def classify_review_reason(
    lineage: DecisionLineage,
    candidate: CandidateRecord | None,
) -> str:
    """Assign primary review reason for triage analysis."""
    if lineage.llm_error:
        return "llm_failure"
    if lineage.llm_decision and lineage.deterministic:
        det_map = {
            "CLEAR_POSITIVE": "MATCH",
            "CLEAR_NEGATIVE": "NO_MATCH",
            "GRAY_ZONE": "REVIEW",
        }
        if det_map.get(lineage.deterministic.decision) != lineage.llm_decision.get(
            "decision"
        ):
            return "divergence"
    if lineage.llm_decision:
        conf = lineage.llm_decision.get("confidence")
        if conf is not None and int(conf) < 60:
            return "low_confidence"
    det = lineage.deterministic
    if det:
        if det.decision == "GRAY_ZONE" and det.confidence < 0.45:
            return "low_margin"
        if det.mixed_scope if hasattr(det, "mixed_scope") else False:
            return "mixed_scope"
        reasons = " ".join(
            [
                getattr(det, "reason", "") or "",
                " ".join(getattr(det, "positive_signals", None) or []),
                " ".join(getattr(det, "negative_signals", None) or []),
            ]
        ).lower()
        if "categoria" in reasons or "category" in reasons:
            return "insufficient_category"
        if "misto" in reasons or "mixed" in reasons or det.mixed_scope:
            return "mixed_scope"
    if candidate:
        if candidate.zero_match_rescue:
            return "zero_match"
        blob = candidate.record.text_blob()
        if len(blob) < 40:
            return "short_text"
        retrieved = set(candidate.retrieved_by or [])
        if "semantic" in retrieved and "lexical" not in retrieved:
            return "semantic_without_keyword"
    return "other"


def analyze_review_queue(
    lineages: list[DecisionLineage],
    candidates_by_id: dict[str, CandidateRecord],
    gold_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Per-reason volume, positive yield, missing docs — for triage."""
    gold_labels = gold_labels or {}
    reviews = [l for l in lineages if l.commercial_decision == "REVIEW"]
    by_reason: dict[str, list[DecisionLineage]] = defaultdict(list)
    for lin in reviews:
        reason = classify_review_reason(lin, candidates_by_id.get(lin.canonical_id))
        by_reason[reason].append(lin)

    groups = {}
    for reason in REVIEW_REASONS:
        items = by_reason.get(reason) or []
        pos_yield = 0
        missing_docs: Counter[str] = Counter()
        for lin in items:
            if gold_labels.get(lin.canonical_id) == "POSITIVE":
                pos_yield += 1
            for d in lin.documents_needed or []:
                missing_docs[str(d)] += 1
        groups[reason] = {
            "volume": len(items),
            "positive_yield": pos_yield,
            "positive_yield_rate": (pos_yield / len(items)) if items else 0.0,
            "missing_documentation": dict(missing_docs.most_common(10)),
            "sample_ids": [l.canonical_id for l in items[:10]],
        }

    n = len(lineages) or 1
    review_rate = len(reviews) / n
    return {
        "review_count": len(reviews),
        "universe_count": len(lineages),
        "review_rate": review_rate,
        "target_review_rate": 0.20,
        "within_target": review_rate <= 0.20,
        "by_reason": groups,
        "triage_layers": [
            "1_deterministic_clear_rules",
            "2_attachments_and_items",
            "3_real_embedding",
            "4_llm",
            "5_human_review",
        ],
        "policy": (
            "Do not reduce review_rate by arbitrary NO_MATCH. "
            "Measure before/after per reason; preserve safe recall."
        ),
        "before_after": {
            "before_review_rate": review_rate,
            "after_review_rate": None,  # filled when triage experiment runs
            "safe_recall_before": None,
            "safe_recall_after": None,
            "statistically_relevant_regression": None,
        },
    }
