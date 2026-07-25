"""Phase 11 — statistical + integrity gates with multi-blocker honesty."""
from __future__ import annotations

from typing import Any

from scripts.ops.hybrid_sector.evaluation.metrics import statistical_power_ok
from scripts.ops.hybrid_sector.evaluation.real_corpus import (
    BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS,
    BLOCKED_INVALID_EVALUATION_CORPUS,
)

INSUFFICIENT_STATISTICAL_POWER = "INSUFFICIENT_STATISTICAL_POWER"

# Multi-blocker terminal family (never collapse to a single soft label)
BLOCKED_REVIEW_CAPACITY = "BLOCKED_REVIEW_CAPACITY"
BLOCKED_LLM_OPERATIONAL_VALIDATION = "BLOCKED_LLM_OPERATIONAL_VALIDATION"
BLOCKED_FULL_SUITE_VALIDATION = "BLOCKED_FULL_SUITE_VALIDATION"
BLOCKED_INSUFFICIENT_RECALL = "BLOCKED_INSUFFICIENT_RECALL"
BLOCKED_INSUFFICIENT_STATISTICAL_POWER = "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"
BLOCKED_UNLABELED_MATCH = "BLOCKED_UNLABELED_MATCH"
BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION = "BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION"
READY_FOR_RECALL_ASSURANCE_REVIEW = "READY_FOR_RECALL_ASSURANCE_REVIEW"

# Operational honest blockers when unready — NOT foundation PR status.
# BLOCKED_REVIEW_CAPACITY is conditional (only with evaluable review data).
# BLOCKED_INVALID_EVALUATION_CORPUS is only for structural/provenance invalidity.
REQUIRED_OPERATIONAL_BLOCKERS_WHEN_UNREADY = (
    BLOCKED_LLM_OPERATIONAL_VALIDATION,
    BLOCKED_FULL_SUITE_VALIDATION,
)

# Back-compat alias used by older imports
REQUIRED_HONEST_BLOCKERS_WHEN_UNREADY = REQUIRED_OPERATIONAL_BLOCKERS_WHEN_UNREADY

NOT_EVALUATED_INSUFFICIENT_REAL_CORPUS = "NOT_EVALUATED_INSUFFICIENT_REAL_CORPUS"
NOT_CHECKED_IN_THIS_EXECUTION = "NOT_CHECKED_IN_THIS_EXECUTION"
CHECKED_BY_CI = "CHECKED_BY_CI"


def _metric_or_null(value: Any, *, n_positives: int) -> float | None:
    """Absence of observations is not 0.0 performance."""
    if n_positives <= 0:
        return None
    if value is None:
        return None
    return float(value)


def evaluate_gates(
    retrieval: dict[str, Any],
    decision: dict[str, Any],
    *,
    audit: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
    corpus_audit: dict[str, Any] | None = None,
    llm_operational: dict[str, Any] | None = None,
    embedding_operational: dict[str, Any] | None = None,
    review_status: dict[str, Any] | None = None,
    full_suite: dict[str, Any] | None = None,
    evaluation_level: str = "B",
    rc_v2_intact: bool | dict[str, Any] | None = None,
) -> dict[str, Any]:
    thr = {
        "retrieval_recall_point": 0.995,
        "retrieval_recall_lower_95": 0.99,
        "preservation_recall_point": 0.995,
        "preservation_recall_lower_95": 0.99,
        "match_precision_point": 0.95,
        "match_precision_lower_95": 0.90,
        "max_review_rate": 0.20,
        **(thresholds or {}),
    }
    n_pos = int(decision.get("n_positives") or retrieval.get("n_gold_positives") or 0)
    power_ok = statistical_power_ok(n_pos)
    observations_present = n_pos > 0

    gates: dict[str, Any] = {
        "statistical_power": {
            "ok": power_ok,
            "n_positives": n_pos,
            "status": "OK" if power_ok else INSUFFICIENT_STATISTICAL_POWER,
        }
    }

    # Integrity: unlabeled MATCH
    unlabeled = int(decision.get("unlabeled_match_count") or decision.get("match_unlabeled") or 0)
    all_m = int(decision.get("all_match_count") or decision.get("match_count") or 0)
    eval_m = int(decision.get("evaluated_match_count") or all_m)
    unlabeled_ok = unlabeled == 0
    denom_ok = all_m == eval_m
    gates["unlabeled_match"] = {
        "pass": unlabeled_ok,
        "unlabeled_match_count": unlabeled,
        "required": "unlabeled_match_count == 0",
    }
    gates["match_denominator"] = {
        "pass": denom_ok,
        "all_match_count": all_m,
        "evaluated_match_count": eval_m,
        "required": "all_match_count == evaluated_match_count",
    }

    # Retrieval gate — null metrics when no positives; never vacuous pass
    r_point = _metric_or_null(retrieval.get("retrieval_recall"), n_positives=n_pos)
    r_low = _metric_or_null(
        retrieval.get("retrieval_recall_lower_95"), n_positives=n_pos
    )
    ret_pass = (
        observations_present
        and r_point is not None
        and r_low is not None
        and r_point >= thr["retrieval_recall_point"]
        and r_low >= thr["retrieval_recall_lower_95"]
        and int(decision.get("critical_false_negatives") or 0) == 0
    )
    gates["retrieval"] = {
        "pass": ret_pass if power_ok else False,
        "point": r_point,
        "lower_95": r_low,
        "blocked_insufficient_power": not power_ok,
        "operational_claim_allowed": (
            evaluation_level == "C" and observations_present and ret_pass and power_ok
        ),
    }

    # Preservation gate (MATCH+REVIEW)
    p_point = _metric_or_null(
        decision.get("safe_recall_match_plus_review"), n_positives=n_pos
    )
    p_low = _metric_or_null(decision.get("safe_recall_lower_95"), n_positives=n_pos)
    crit_fn = int(decision.get("critical_false_negatives") or 0)
    pres_pass = (
        observations_present
        and p_point is not None
        and p_low is not None
        and p_point >= thr["preservation_recall_point"]
        and p_low >= thr["preservation_recall_lower_95"]
        and crit_fn == 0
    )
    gates["preservation"] = {
        "pass": pres_pass if power_ok else False,
        "point": p_point,
        "lower_95": p_low,
        "critical_false_negatives": crit_fn,
        "blocked_insufficient_power": not power_ok,
        "operational_claim_allowed": (
            evaluation_level == "C" and observations_present and pres_pass and power_ok
        ),
    }

    # Commercial MATCH precision — primary is all MATCH, not hard-only.
    # Vacuous 0-MATCH / 0-positives must NOT pass (no free 1.0 or 0.0 as evidence).
    raw_point = decision.get("match_precision_all")
    if raw_point is None:
        raw_point = decision.get("match_precision")
    precision_vacuous = (
        bool(decision.get("precision_vacuous"))
        or raw_point is None
        or not observations_present
    )
    all_match_n = int(decision.get("all_match_count") or decision.get("match_count") or 0)
    if precision_vacuous or all_match_n == 0 or not observations_present:
        m_point = None
        m_low = None
        m_cons = None
        precision_evidence_ok = False
    else:
        m_point = float(raw_point)
        m_low_raw = decision.get("match_precision_lower_95")
        m_low = float(m_low_raw) if m_low_raw is not None else None
        cons_raw = decision.get("match_precision_conservative")
        m_cons = float(cons_raw) if cons_raw is not None else m_point
        precision_evidence_ok = bool(decision.get("precision_evidence_sufficient", True))
    hard_fp = int(decision.get("match_false_positives_hard") or 0)
    ambig_risk = int(decision.get("ambiguous_match_commercial_risk") or 0)
    com_pass = (
        observations_present
        and precision_evidence_ok
        and not precision_vacuous
        and all_match_n > 0
        and m_point is not None
        and m_low is not None
        and m_cons is not None
        and m_point >= thr["match_precision_point"]
        and m_low >= thr["match_precision_lower_95"]
        and m_cons >= thr["match_precision_point"]
        and hard_fp == 0
        and unlabeled_ok
        and denom_ok
        and ambig_risk == 0
    )
    commercial_ops_allowed = (
        evaluation_level == "C"
        and observations_present
        and com_pass
        and not precision_vacuous
        and all_match_n > 0
    )
    gates["commercial"] = {
        "pass": com_pass,
        "point": m_point,
        "lower_95": m_low,
        "conservative": m_cons,
        "hard_only_additional": decision.get("match_precision_hard_only"),
        "hard_false_positives": hard_fp,
        "ambiguous_match_commercial_risk": ambig_risk,
        "all_match_count": all_match_n,
        "precision_vacuous": precision_vacuous or not observations_present,
        "blocks_readiness": not com_pass,
        "operational_claim_allowed": commercial_ops_allowed,
    }

    # Audit gate
    audit = audit or {}
    audit_pass = (
        int(audit.get("invented_evidence_accepted") or 0) == 0
        and float(audit.get("llm_error_to_review_rate") or 1.0) >= 1.0
        and float(audit.get("lineage_coverage") or 0.0) >= 1.0
        and int(audit.get("silent_discards") or 0) == 0
    )
    gates["audit"] = {
        "pass": audit_pass,
        "details": audit,
    }

    # Corpus authenticity
    corpus_audit = corpus_audit or {}
    corpus_ok = bool(corpus_audit.get("operational_gold_eligible"))
    corpus_blockers = list(corpus_audit.get("blockers") or [])
    # Level B/A synthetic cannot sustain operational claims — but only attach
    # INVALID when the corpus is synthetic/invalid, not when Level C is merely empty.
    if evaluation_level != "C":
        corpus_ok = False
        if BLOCKED_INVALID_EVALUATION_CORPUS not in corpus_blockers:
            # Prefer keeping existing blockers; add INVALID only if no insufficient marker
            # for synthetic/unit evaluation of non-real corpora.
            if BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS not in corpus_blockers:
                corpus_blockers.append(BLOCKED_INVALID_EVALUATION_CORPUS)
    gates["corpus"] = {
        "pass": corpus_ok,
        "evaluation_level": evaluation_level,
        "blockers": corpus_blockers,
        "audit": {
            k: corpus_audit.get(k)
            for k in (
                "corpus_kind",
                "operational_gold_eligible",
                "quotas",
                "dual_review",
                "n_records",
                "n_locked",
            )
        },
    }

    # LLM operational validation (≥200 stratified real, human review)
    llm_operational = llm_operational or {}
    llm_ok = bool(llm_operational.get("passed"))
    gates["llm_operational"] = {
        "pass": llm_ok,
        "artifact_present": bool(llm_operational),
        "passed": llm_ok,
        "status": llm_operational.get("status") or BLOCKED_LLM_OPERATIONAL_VALIDATION,
        "n_samples": llm_operational.get("n_samples") or 0,
        "min_required": llm_operational.get("min_required") or 200,
        "human_review_complete": bool(llm_operational.get("human_review_complete")),
    }

    # Embedding operational
    embedding_operational = embedding_operational or {}
    emb_ok = bool(embedding_operational.get("passed"))
    gates["embedding_operational"] = {
        "pass": emb_ok,
        "artifact_present": bool(embedding_operational),
        "passed": emb_ok,
        "status": embedding_operational.get("status")
        or BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION,
        "provider_class": embedding_operational.get("provider_class"),
        "benchmark": embedding_operational.get("benchmark_summary"),
    }

    # Review capacity — empty/vacuous universe is NOT proof of capacity and must
    # NOT activate BLOCKED_REVIEW_CAPACITY.
    review_status = review_status or {}
    review_rate_raw = decision.get("review_rate")
    review_count = int(review_status.get("review_count") or 0)
    overflow = review_status.get("operational_status") == "OPERATIONALLY_BLOCKED_REVIEW_VOLUME"
    # Evaluable only with real Level C gold + eligible corpus + observations.
    # Zero positives / zero records / non-C → NOT_EVALUATED (blocker inactive).
    evaluable_review_universe = (
        observations_present
        and evaluation_level == "C"
        and corpus_ok
        and n_pos > 0
    )
    if not evaluable_review_universe:
        review_ok = False
        review_blocker_active = False
        review_status_label = NOT_EVALUATED_INSUFFICIENT_REAL_CORPUS
        review_rate: float | None = None
        within_numeric = False
    else:
        review_rate = float(review_rate_raw or 0)
        within_numeric = (not overflow) and review_rate <= float(thr["max_review_rate"])
        review_ok = (
            evaluation_level == "C"
            and corpus_ok
            and power_ok
            and within_numeric
            and not overflow
        )
        review_blocker_active = not review_ok
        review_status_label = (
            "WITHIN_CAPACITY"
            if review_ok
            else BLOCKED_REVIEW_CAPACITY
        )

    gates["review_capacity"] = {
        "status": review_status_label,
        "pass": review_ok,
        "blocker_active": review_blocker_active,
        "review_rate": review_rate,
        "max_review_rate": thr["max_review_rate"],
        "overflow": overflow,
        "within_numeric": within_numeric,
        "review_count": review_count,
        "operational_status": review_status.get("operational_status"),
        "vacuous_empty_not_pass": not review_ok,
        "evaluable": evaluable_review_universe,
    }

    # Full suite
    full_suite = full_suite or {}
    suite_ok = bool(full_suite.get("passed") or full_suite.get("pass"))
    gates["full_suite"] = {
        "pass": suite_ok,
        "artifact_present": bool(full_suite),
        "passed": suite_ok,
        "status": full_suite.get("status") or BLOCKED_FULL_SUITE_VALIDATION,
        "details": full_suite.get("details"),
    }

    # RC v2 — never claim false when unchecked in this execution
    rc_gate = _normalize_rc_v2(rc_v2_intact)
    gates["rc_v2_intact"] = rc_gate
    rc_v2_pass = rc_gate.get("passed") is True

    # Collect ALL active blockers (honest multi-status)
    active_blockers: list[str] = []
    if not corpus_ok:
        # Prefer corpus-reported blockers; default insufficient for empty Level C
        if corpus_blockers:
            active_blockers.extend(corpus_blockers)
        elif evaluation_level == "C":
            active_blockers.append(BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS)
        else:
            active_blockers.append(BLOCKED_INVALID_EVALUATION_CORPUS)
        if (
            evaluation_level == "C"
            and not quotas_ok(corpus_audit)
            and BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS not in active_blockers
        ):
            active_blockers.append(BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS)
    if not power_ok:
        active_blockers.append(BLOCKED_INSUFFICIENT_STATISTICAL_POWER)
    if not unlabeled_ok:
        active_blockers.append(BLOCKED_UNLABELED_MATCH)
    if not denom_ok:
        active_blockers.append(BLOCKED_UNLABELED_MATCH)
    # Recall blockers only when observations exist and fail thresholds
    if observations_present and power_ok and (not ret_pass or not pres_pass):
        active_blockers.append(BLOCKED_INSUFFICIENT_RECALL)
    if observations_present and not com_pass and unlabeled_ok:
        # commercial fail with observations is recall/precision integrity issue
        if BLOCKED_INSUFFICIENT_RECALL not in active_blockers:
            active_blockers.append(BLOCKED_INSUFFICIENT_RECALL)
    if not audit_pass and observations_present:
        active_blockers.append(BLOCKED_LLM_OPERATIONAL_VALIDATION)
    if not llm_ok:
        active_blockers.append(BLOCKED_LLM_OPERATIONAL_VALIDATION)
    if not emb_ok:
        active_blockers.append(BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION)
    # REVIEW capacity only when evaluable and failing
    if review_blocker_active:
        active_blockers.append(BLOCKED_REVIEW_CAPACITY)
    if not suite_ok:
        active_blockers.append(BLOCKED_FULL_SUITE_VALIDATION)
    if rc_gate.get("passed") is False:
        active_blockers.append("BLOCKED_RC_V2_INTEGRITY")

    all_core = (
        corpus_ok
        and power_ok
        and ret_pass
        and pres_pass
        and com_pass
        and audit_pass
        and unlabeled_ok
        and denom_ok
        and llm_ok
        and emb_ok
        and review_ok
        and suite_ok
        and rc_v2_pass
        and evaluation_level == "C"
        and observations_present
        and not precision_vacuous
    )

    # Surface required operational blockers when not READY (not review-capacity-by-default)
    if not all_core:
        for req in REQUIRED_OPERATIONAL_BLOCKERS_WHEN_UNREADY:
            if req not in active_blockers:
                active_blockers.append(req)

    active_blockers = sorted(set(active_blockers))

    if all_core:
        terminal = READY_FOR_RECALL_ASSURANCE_REVIEW
        primary_terminal = terminal
        active_blockers = [
            b
            for b in active_blockers
            if b not in REQUIRED_OPERATIONAL_BLOCKERS_WHEN_UNREADY
        ]
    else:
        # Primary terminal: severity-ordered. Insufficient real gold before invalid.
        priority = [
            BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS,
            BLOCKED_INVALID_EVALUATION_CORPUS,
            BLOCKED_UNLABELED_MATCH,
            BLOCKED_INSUFFICIENT_STATISTICAL_POWER,
            BLOCKED_INSUFFICIENT_RECALL,
            BLOCKED_LLM_OPERATIONAL_VALIDATION,
            BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION,
            BLOCKED_REVIEW_CAPACITY,
            BLOCKED_FULL_SUITE_VALIDATION,
            "BLOCKED_RC_V2_INTEGRITY",
        ]
        primary_terminal = next(
            (b for b in priority if b in active_blockers),
            BLOCKED_INSUFFICIENT_RECALL,
        )
        terminal = primary_terminal

    honest_present = all_core or all(
        b in active_blockers for b in REQUIRED_OPERATIONAL_BLOCKERS_WHEN_UNREADY
    )

    return {
        "gates": gates,
        "thresholds": thr,
        "all_core_pass": all_core,
        "terminal_status": terminal,
        "primary_terminal_status": primary_terminal,
        "active_blockers": active_blockers,
        "required_honest_blockers": list(REQUIRED_OPERATIONAL_BLOCKERS_WHEN_UNREADY),
        "required_honest_blockers_present": honest_present,
        "evaluation_level": evaluation_level,
        "operational_claim_allowed": (
            evaluation_level == "C"
            and observations_present
            and commercial_ops_allowed
            and gates["retrieval"]["operational_claim_allowed"]
            and gates["preservation"]["operational_claim_allowed"]
        ),
        "ready_requirements": {
            "real_corpus_sufficient": corpus_ok,
            "label_provenance_valid": bool(
                (corpus_audit.get("dual_review") or {}).get("ok")
            )
            if corpus_audit
            else False,
            "unlabeled_match_zero": unlabeled_ok,
            "real_recall_approved": (
                ret_pass
                and pres_pass
                and power_ok
                and evaluation_level == "C"
                and observations_present
            ),
            "real_precision_approved": (
                com_pass
                and evaluation_level == "C"
                and observations_present
                and not precision_vacuous
                and all_match_n > 0
            ),
            "real_embeddings_evaluated": emb_ok,
            "real_llm_validated": llm_ok,
            "review_capacity_within_limit": review_ok,
            "full_suite_green": suite_ok,
            "rc_v2_intact": rc_v2_pass,
        },
    }


def _normalize_rc_v2(rc_v2_intact: bool | dict[str, Any] | None) -> dict[str, Any]:
    """RC v2 check object — never write passed=false when not checked locally."""
    if isinstance(rc_v2_intact, dict):
        status = str(rc_v2_intact.get("status") or NOT_CHECKED_IN_THIS_EXECUTION)
        passed = rc_v2_intact.get("passed")
        if status == NOT_CHECKED_IN_THIS_EXECUTION:
            passed = None
        out: dict[str, Any] = {
            "status": status,
            "passed": passed,
            "checked": status != NOT_CHECKED_IN_THIS_EXECUTION,
        }
        for k in ("workflow", "tested_sha", "value"):
            if k in rc_v2_intact:
                out[k] = rc_v2_intact[k]
        return out
    if rc_v2_intact is True:
        return {
            "status": CHECKED_BY_CI,
            "passed": True,
            "checked": True,
            "value": True,
        }
    if rc_v2_intact is False:
        return {
            "status": "CHECKED_FAILED",
            "passed": False,
            "checked": True,
            "value": False,
        }
    return {
        "status": NOT_CHECKED_IN_THIS_EXECUTION,
        "passed": None,
        "checked": False,
        "value": None,
    }


def quotas_ok(corpus_audit: dict[str, Any]) -> bool:
    q = corpus_audit.get("quotas") or {}
    return bool(q.get("ok"))
