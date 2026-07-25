"""Phase 10 — stage metrics (never a single accuracy; never dilute MATCH denominators)."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

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
    # Absence of positives is not zero recall — report null for operational honesty
    recall = (len(retrieved_pos) / n_pos) if n_pos else None

    by_channel: dict[str, set[str]] = defaultdict(set)
    for c in candidates:
        for ch in c.retrieved_by:
            by_channel[ch].add(c.record.canonical_id)

    recall_by_channel = {
        ch: (len(ids & gold_positive_ids) / n_pos if n_pos else None)
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
        "retrieval_recall_lower_95": (
            binomial_ci_lower_one_sided(len(retrieved_pos), n_pos) if n_pos else None
        ),
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
    adjudicated_ids: set[str] | None = None,
) -> dict[str, Any]:
    """gold_labels: id -> POSITIVE|NEGATIVE|AMBIGUOUS (human).

    Precision rules (integrity):
    - Primary commercial precision is over ALL MATCH predictions.
    - unlabeled MATCH is a hard integrity failure (count tracked).
    - Conservative precision treats unadjudicated AMBIGUOUS MATCH as error.
    - Hard-label-only precision is ADDITIONAL, never the sole primary gate metric.
    - Gate: all_match_count == evaluated_match_count (no convenient subset).
    """
    critical_positive_ids = critical_positive_ids or set()
    adjudicated_ids = adjudicated_ids or set()
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
    # Null when no positives — do not treat absence as 0.0 or 1.0 performance
    safe_recall = (preserved / n_pos) if n_pos else None

    match_ids = [l.canonical_id for l in lineages if l.commercial_decision == "MATCH"]
    all_match_count = len(match_ids)

    unlabeled_match_ids = [m for m in match_ids if m not in gold_labels]
    unlabeled_match_count = len(unlabeled_match_ids)

    # Every MATCH must be evaluated — no unlabeled allowed in locked eval
    evaluated_match_ids = list(match_ids)  # evaluate ALL matches
    evaluated_match_count = len(evaluated_match_ids)

    # --- Primary precision: over ALL MATCH (never vacuous 1.0 on empty) ---
    # TP = gold POSITIVE only. Denom = every MATCH (NEG + AMBIG + unlabeled hurt).
    tp_all = sum(1 for m in match_ids if gold_labels.get(m) == "POSITIVE")
    fp_hard = sum(1 for m in match_ids if gold_labels.get(m) == "NEGATIVE")
    ambiguous_match = sum(1 for m in match_ids if gold_labels.get(m) == "AMBIGUOUS")
    ambig_unadj_as_error = sum(
        1
        for m in match_ids
        if gold_labels.get(m) == "AMBIGUOUS" and m not in adjudicated_ids
    )
    ambig_adjudicated = ambiguous_match - ambig_unadj_as_error

    # Empty MATCH set is NOT perfect precision — insufficient evidence.
    labeled_hard_matches = [
        m for m in match_ids if gold_labels.get(m) in {"POSITIVE", "NEGATIVE"}
    ]
    tp_hard = sum(1 for m in labeled_hard_matches if gold_labels[m] == "POSITIVE")
    conservative_errors = fp_hard + ambig_unadj_as_error + unlabeled_match_count

    if all_match_count == 0:
        match_precision_all = None
        match_precision_conservative = None
        match_precision_hard_only = None
        precision_vacuous = True
    else:
        precision_vacuous = False
        # Primary over ALL MATCH: only gold POSITIVE counts as success.
        match_precision_all = tp_all / all_match_count

        # Conservative: unadjudicated AMBIGUOUS is an explicit error with extra
        # penalty in the denominator (all_match + unadj_ambig), so whenever
        # ambig_unadj > 0 the conservative rate is strictly below primary.
        # Adjudicated AMBIGUOUS does not add extra penalty (resolved).
        # Formula: tp / (all_match_count + ambig_unadj_as_error)
        cons_denom = all_match_count + ambig_unadj_as_error
        match_precision_conservative = tp_all / cons_denom

        match_precision_hard_only = (
            tp_hard / len(labeled_hard_matches) if labeled_hard_matches else None
        )

    # Integrity gates
    unlabeled_match_gate_ok = unlabeled_match_count == 0
    all_equals_evaluated = all_match_count == evaluated_match_count

    review_ids = [l.canonical_id for l in lineages if l.commercial_decision == "REVIEW"]
    review_rate = len(review_ids) / len(lineages) if lineages else 0.0
    review_yield = (
        sum(1 for r in review_ids if gold_labels.get(r) == "POSITIVE") / len(review_ids)
        if review_ids
        else 0.0
    )

    llm_rescue = 0
    disagreement = 0
    for lin in lineages:
        if not lin.llm_invoked or not lin.deterministic:
            continue
        if (
            lin.deterministic.decision == "CLEAR_NEGATIVE"
            and lin.commercial_decision in {"MATCH", "REVIEW"}
            and gold_labels.get(lin.canonical_id) == "POSITIVE"
        ):
            llm_rescue += 1
        if lin.llm_decision:
            det_map = {
                "CLEAR_POSITIVE": "MATCH",
                "CLEAR_NEGATIVE": "NO_MATCH",
                "GRAY_ZONE": "REVIEW",
            }
            if det_map.get(lin.deterministic.decision) != lin.llm_decision.get(
                "decision"
            ):
                disagreement += 1

    ambiguous_match_commercial_risk = ambig_unadj_as_error

    precision_lower = (
        binomial_ci_lower_one_sided(tp_all, all_match_count)
        if all_match_count and n_pos
        else None
    )

    return {
        "safe_recall_match_plus_review": safe_recall,
        "safe_recall_lower_95": (
            binomial_ci_lower_one_sided(preserved, n_pos) if n_pos else None
        ),
        "false_negative_rate_no_match": fn_no_match / n_pos if n_pos else None,
        "critical_false_negatives": critical_fn,
        "n_positives": n_pos,
        "n_preserved": preserved,
        # Primary commercial precision (all MATCH) — None when vacuous
        "match_precision": match_precision_all,
        "match_precision_all": match_precision_all,
        "match_precision_lower_95": precision_lower,
        "precision_vacuous": precision_vacuous,
        "precision_evidence_sufficient": all_match_count > 0 and n_pos > 0,
        # Conservative: unadjudicated AMBIGUOUS as error; adj AMBIG excluded from denom
        "match_precision_conservative": match_precision_conservative,
        "match_precision_conservative_errors": conservative_errors,
        "ambiguous_match_unadjudicated_as_error": ambig_unadj_as_error,
        "ambiguous_match_adjudicated": ambig_adjudicated,
        "ambiguous_match_commercial_risk": ambiguous_match_commercial_risk,
        # Additional hard-label-only (NOT primary)
        "match_precision_hard_only": match_precision_hard_only,
        "match_precision_hard_only_is_primary": False,
        "match_labeled_hard_count": len(labeled_hard_matches),
        "match_true_positives": tp_all,
        "match_false_positives_hard": fp_hard,
        "match_ambiguous": ambiguous_match,
        "match_unlabeled": unlabeled_match_count,
        "unlabeled_match_count": unlabeled_match_count,
        "unlabeled_match_ids": unlabeled_match_ids[:50],
        "unlabeled_match_gate_ok": unlabeled_match_gate_ok,
        "all_match_count": all_match_count,
        "evaluated_match_count": evaluated_match_count,
        "all_match_count_equals_evaluated": all_equals_evaluated,
        "match_count": all_match_count,  # alias
        "review_rate": review_rate,
        "review_yield": review_yield,
        "llm_rescue_rate": llm_rescue / n_pos if n_pos else None,
        "deterministic_llm_disagreement": disagreement,
        "n_negatives_gold": len(neg_ids),
        "n_lineages": len(lineages),
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
