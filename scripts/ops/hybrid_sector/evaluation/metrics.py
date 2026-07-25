"""Phase 10 — stage metrics (never a single accuracy)."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

from scripts.ops.hybrid_sector.models import CandidateRecord, DecisionLineage


def binomial_ci_lower_one_sided(successes: int, n: int, alpha: float = 0.05) -> float:
    """Clopper-Pearson style one-sided lower bound via beta quantile approximation.

    Uses normal approx with continuity for large n; exact-ish for small n via
    Clopper-Pearson lower: Beta(alpha; k, n-k+1) when k>0; 0 when k==0.
    """
    if n <= 0:
        return 0.0
    if successes <= 0:
        return 0.0
    if successes >= n:
        # lower bound for p when all successes: alpha^(1/n)
        return float(alpha ** (1.0 / n))

    # Wilson score lower bound (one-sided approx with z for 95%)
    z = 1.6448536269514722  # Phi^{-1}(0.95)
    phat = successes / n
    denom = 1 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def statistical_power_ok(n_positives: int, *, min_for_99: int = 300) -> bool:
    """Rule-of-thumb: need ≥300 positives with ~0 FN for lower CI ≈99%."""
    return n_positives >= min_for_99


def retrieval_metrics(
    gold_positive_ids: set[str],
    candidates: list[CandidateRecord],
    *,
    gold_meta: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gold_meta = gold_meta or {}
    cand_ids = {c.record.canonical_id for c in candidates}
    retrieved_pos = gold_positive_ids & cand_ids
    n_pos = len(gold_positive_ids)
    recall = len(retrieved_pos) / n_pos if n_pos else 0.0

    by_channel: dict[str, set[str]] = defaultdict(set)
    for c in candidates:
        for ch in c.retrieved_by:
            by_channel[ch].add(c.record.canonical_id)

    recall_by_channel = {
        ch: (len(ids & gold_positive_ids) / n_pos if n_pos else 0.0)
        for ch, ids in by_channel.items()
    }

    # without keywords: gold positives marked has_keyword=False
    no_kw = {
        gid
        for gid in gold_positive_ids
        if not gold_meta.get(gid, {}).get("has_keyword", True)
    }
    recall_without_kw = (
        len(no_kw & cand_ids) / len(no_kw) if no_kw else None
    )

    unique_rescues = {}
    lexical_ids = by_channel.get("lexical", set())
    for ch, ids in by_channel.items():
        if ch == "lexical":
            continue
        unique_rescues[ch] = len((ids - lexical_ids) & gold_positive_ids)

    return {
        "retrieval_recall": recall,
        "retrieval_recall_lower_95": binomial_ci_lower_one_sided(len(retrieved_pos), n_pos),
        "n_gold_positives": n_pos,
        "n_retrieved_positives": len(retrieved_pos),
        "missed_positive_ids": sorted(gold_positive_ids - cand_ids),
        "recall_by_channel": recall_by_channel,
        "recall_without_keywords": recall_without_kw,
        "unique_rescues_by_channel": unique_rescues,
    }


def decision_metrics(
    gold_labels: dict[str, str],
    lineages: list[DecisionLineage],
    *,
    critical_positive_ids: set[str] | None = None,
) -> dict[str, Any]:
    """gold_labels: id -> POSITIVE|NEGATIVE|AMBIGUOUS (human)."""
    critical_positive_ids = critical_positive_ids or set()
    by_id = {l.canonical_id: l for l in lineages}
    pos_ids = {i for i, lab in gold_labels.items() if lab == "POSITIVE"}
    neg_ids = {i for i, lab in gold_labels.items() if lab == "NEGATIVE"}

    # Safe recall: positive preserved as MATCH or REVIEW
    preserved = 0
    fn_no_match = 0
    critical_fn = 0
    for pid in pos_ids:
        lin = by_id.get(pid)
        if lin is None:
            fn_no_match += 1
            if pid in critical_positive_ids:
                critical_fn += 1
            continue
        if lin.commercial_decision in {"MATCH", "REVIEW"}:
            preserved += 1
        elif lin.commercial_decision == "NO_MATCH":
            fn_no_match += 1
            if pid in critical_positive_ids:
                critical_fn += 1

    n_pos = len(pos_ids)
    safe_recall = preserved / n_pos if n_pos else 0.0

    # Commercial MATCH precision — only on gold-labeled hard cases (POSITIVE/NEGATIVE).
    # Unlabeled distractors and AMBIGUOUS must not dilute the denominator.
    match_ids = [l.canonical_id for l in lineages if l.commercial_decision == "MATCH"]
    labeled_hard_matches = [
        m for m in match_ids if gold_labels.get(m) in {"POSITIVE", "NEGATIVE"}
    ]
    tp = sum(1 for m in labeled_hard_matches if gold_labels[m] == "POSITIVE")
    fp = sum(1 for m in labeled_hard_matches if gold_labels[m] == "NEGATIVE")
    ambiguous_match = sum(1 for m in match_ids if gold_labels.get(m) == "AMBIGUOUS")
    unlabeled_match = sum(1 for m in match_ids if m not in gold_labels)
    precision = tp / len(labeled_hard_matches) if labeled_hard_matches else 1.0

    review_ids = [l.canonical_id for l in lineages if l.commercial_decision == "REVIEW"]
    review_rate = len(review_ids) / len(lineages) if lineages else 0.0
    review_yield = (
        sum(1 for r in review_ids if gold_labels.get(r) == "POSITIVE") / len(review_ids)
        if review_ids
        else 0.0
    )

    llm_rescue = 0
    disagreement = 0
    for l in lineages:
        if not l.llm_invoked or not l.deterministic:
            continue
        if (
            l.deterministic.decision == "CLEAR_NEGATIVE"
            and l.commercial_decision in {"MATCH", "REVIEW"}
            and gold_labels.get(l.canonical_id) == "POSITIVE"
        ):
            llm_rescue += 1
        if l.llm_decision:
            det_map = {
                "CLEAR_POSITIVE": "MATCH",
                "CLEAR_NEGATIVE": "NO_MATCH",
                "GRAY_ZONE": "REVIEW",
            }
            if det_map.get(l.deterministic.decision) != l.llm_decision.get("decision"):
                disagreement += 1

    return {
        "safe_recall_match_plus_review": safe_recall,
        "safe_recall_lower_95": binomial_ci_lower_one_sided(preserved, n_pos),
        "false_negative_rate_no_match": fn_no_match / n_pos if n_pos else 0.0,
        "critical_false_negatives": critical_fn,
        "n_positives": n_pos,
        "n_preserved": preserved,
        "match_precision": precision,
        "match_precision_lower_95": binomial_ci_lower_one_sided(tp, len(labeled_hard_matches))
        if labeled_hard_matches
        else 1.0,
        "match_count": len(match_ids),
        "match_labeled_hard_count": len(labeled_hard_matches),
        "match_true_positives": tp,
        "match_false_positives_hard": fp,
        "match_ambiguous": ambiguous_match,
        "match_unlabeled": unlabeled_match,
        "review_rate": review_rate,
        "review_yield": review_yield,
        "llm_rescue_rate": llm_rescue / n_pos if n_pos else 0.0,
        "deterministic_llm_disagreement": disagreement,
        "n_negatives_gold": len(neg_ids),
    }


def confusion_counts(
    gold_labels: dict[str, str],
    lineages: list[DecisionLineage],
) -> dict[str, Any]:
    """3-way commercial vs POSITIVE/NEGATIVE/AMBIGUOUS gold."""
    by_id = {l.canonical_id: l.commercial_decision for l in lineages}
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for gid, glab in gold_labels.items():
        pred = by_id.get(gid, "MISSING")
        matrix[glab][pred] += 1
    return {k: dict(v) for k, v in matrix.items()}
