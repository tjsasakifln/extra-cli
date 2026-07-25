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

# Statuses that MUST appear until evidence clears them (report list, not single)
REQUIRED_HONEST_BLOCKERS_WHEN_UNREADY = (
    BLOCKED_INVALID_EVALUATION_CORPUS,
    BLOCKED_LLM_OPERATIONAL_VALIDATION,
    BLOCKED_REVIEW_CAPACITY,
    BLOCKED_FULL_SUITE_VALIDATION,
)


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
    rc_v2_intact: bool | None = None,
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

    # Retrieval gate — only Level C can sustain operational claims
    r_point = float(retrieval.get("retrieval_recall") or 0)
    r_low = float(retrieval.get("retrieval_recall_lower_95") or 0)
    ret_pass = (
        r_point >= thr["retrieval_recall_point"]
        and r_low >= thr["retrieval_recall_lower_95"]
        and int(decision.get("critical_false_negatives") or 0) == 0
    )
    gates["retrieval"] = {
        "pass": ret_pass if power_ok else False,
        "point": r_point,
        "lower_95": r_low,
        "blocked_insufficient_power": not power_ok,
        "operational_claim_allowed": evaluation_level == "C",
    }

    # Preservation gate (MATCH+REVIEW)
    p_point = float(decision.get("safe_recall_match_plus_review") or 0)
    p_low = float(decision.get("safe_recall_lower_95") or 0)
    crit_fn = int(decision.get("critical_false_negatives") or 0)
    pres_pass = (
        p_point >= thr["preservation_recall_point"]
        and p_low >= thr["preservation_recall_lower_95"]
        and crit_fn == 0
    )
    gates["preservation"] = {
        "pass": pres_pass if power_ok else False,
        "point": p_point,
        "lower_95": p_low,
        "critical_false_negatives": crit_fn,
        "blocked_insufficient_power": not power_ok,
        "operational_claim_allowed": evaluation_level == "C",
    }

    # Commercial MATCH precision — primary is all MATCH, not hard-only.
    # Vacuous 0-MATCH must NOT pass (no free 1.0 precision).
    raw_point = decision.get("match_precision_all")
    if raw_point is None:
        raw_point = decision.get("match_precision")
    precision_vacuous = bool(decision.get("precision_vacuous")) or raw_point is None
    all_match_n = int(decision.get("all_match_count") or decision.get("match_count") or 0)
    if precision_vacuous or all_match_n == 0:
        m_point = 0.0
        m_low = 0.0
        m_cons = 0.0
        precision_evidence_ok = False
    else:
        m_point = float(raw_point)
        m_low = float(decision.get("match_precision_lower_95") or 0)
        cons_raw = decision.get("match_precision_conservative")
        m_cons = float(cons_raw) if cons_raw is not None else m_point
        precision_evidence_ok = bool(decision.get("precision_evidence_sufficient", True))
    hard_fp = int(decision.get("match_false_positives_hard") or 0)
    ambig_risk = int(decision.get("ambiguous_match_commercial_risk") or 0)
    com_pass = (
        precision_evidence_ok
        and not precision_vacuous
        and all_match_n > 0
        and m_point >= thr["match_precision_point"]
        and m_low >= thr["match_precision_lower_95"]
        and m_cons >= thr["match_precision_point"]  # conservative must also clear
        and hard_fp == 0
        and unlabeled_ok
        and denom_ok
        and ambig_risk == 0  # unadjudicated AMBIGUOUS MATCH fails until adjudicated
    )
    # Operational commercial claims only on Level C with real evidence — never vacuous
    commercial_ops_allowed = (
        evaluation_level == "C" and com_pass and not precision_vacuous and all_match_n > 0
    )
    gates["commercial"] = {
        "pass": com_pass,
        "point": m_point if not precision_vacuous else None,
        "lower_95": m_low if not precision_vacuous else None,
        "conservative": m_cons if not precision_vacuous else None,
        "hard_only_additional": decision.get("match_precision_hard_only"),
        "hard_false_positives": hard_fp,
        "ambiguous_match_commercial_risk": ambig_risk,
        "all_match_count": all_match_n,
        "precision_vacuous": precision_vacuous,
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
    if evaluation_level != "C":
        corpus_ok = False
        if BLOCKED_INVALID_EVALUATION_CORPUS not in corpus_blockers:
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
        "status": embedding_operational.get("status")
        or BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION,
        "provider_class": embedding_operational.get("provider_class"),
        "benchmark": embedding_operational.get("benchmark_summary"),
    }

    # Review capacity — empty/vacuous universe is NOT proof of capacity.
    # Require real operational evidence (Level C + corpus_ok + enough decisions)
    # before clearing BLOCKED_REVIEW_CAPACITY.
    review_status = review_status or {}
    review_rate = float(decision.get("review_rate") or 0)
    n_lineages = int(decision.get("n_lineages") or 0)
    # decision may not carry n_lineages; infer from review_rate context via review_status
    review_count = int(review_status.get("review_count") or 0)
    overflow = review_status.get("operational_status") == "OPERATIONALLY_BLOCKED_REVIEW_VOLUME"
    within_numeric = (not overflow) and review_rate <= float(thr["max_review_rate"])
    # Vacuous: no gold power / no real corpus → cannot claim capacity cleared
    review_evidence_ok = (
        evaluation_level == "C"
        and corpus_ok
        and power_ok
        and within_numeric
        and not overflow
    )
    review_ok = review_evidence_ok
    gates["review_capacity"] = {
        "pass": review_ok,
        "review_rate": review_rate,
        "max_review_rate": thr["max_review_rate"],
        "overflow": overflow,
        "within_numeric": within_numeric,
        "review_count": review_count,
        "operational_status": review_status.get("operational_status"),
        "vacuous_empty_not_pass": not review_evidence_ok,
    }

    # Full suite
    full_suite = full_suite or {}
    suite_ok = bool(full_suite.get("passed"))
    gates["full_suite"] = {
        "pass": suite_ok,
        "status": full_suite.get("status") or BLOCKED_FULL_SUITE_VALIDATION,
        "details": full_suite.get("details"),
    }

    # RC v2
    gates["rc_v2_intact"] = {
        "pass": rc_v2_intact is True,
        "checked": rc_v2_intact is not None,
        "value": rc_v2_intact,
    }

    # Collect ALL active blockers (honest multi-status)
    active_blockers: list[str] = []
    if not corpus_ok:
        active_blockers.extend(corpus_blockers or [BLOCKED_INVALID_EVALUATION_CORPUS])
        if not quotas_ok(corpus_audit):
            active_blockers.append(BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS)
    if not power_ok:
        active_blockers.append(BLOCKED_INSUFFICIENT_STATISTICAL_POWER)
    if not unlabeled_ok:
        active_blockers.append(BLOCKED_UNLABELED_MATCH)
    if not denom_ok:
        active_blockers.append(BLOCKED_UNLABELED_MATCH)
    if power_ok and (not ret_pass or not pres_pass):
        active_blockers.append(BLOCKED_INSUFFICIENT_RECALL)
    if not com_pass and unlabeled_ok:
        active_blockers.append(BLOCKED_INSUFFICIENT_RECALL)
    if not audit_pass:
        active_blockers.append(BLOCKED_LLM_OPERATIONAL_VALIDATION)
    if not llm_ok:
        active_blockers.append(BLOCKED_LLM_OPERATIONAL_VALIDATION)
    if not emb_ok:
        active_blockers.append(BLOCKED_EMBEDDING_OPERATIONAL_VALIDATION)
    if not review_ok:
        active_blockers.append(BLOCKED_REVIEW_CAPACITY)
    if not suite_ok:
        active_blockers.append(BLOCKED_FULL_SUITE_VALIDATION)
    if rc_v2_intact is False:
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
        and rc_v2_intact is True
        and evaluation_level == "C"
        and not precision_vacuous
    )

    # Always surface the four required honest blockers when not READY.
    # They remain until cleared by real evidence (READY), not by vacuous empty runs.
    if not all_core:
        for req in REQUIRED_HONEST_BLOCKERS_WHEN_UNREADY:
            if req not in active_blockers:
                active_blockers.append(req)

    active_blockers = sorted(set(active_blockers))

    if all_core:
        terminal = READY_FOR_RECALL_ASSURANCE_REVIEW
        primary_terminal = terminal
        # READY clears the four honest blockers
        active_blockers = [
            b for b in active_blockers if b not in REQUIRED_HONEST_BLOCKERS_WHEN_UNREADY
        ]
    else:
        # Primary terminal: first severity-ordered blocker
        priority = [
            BLOCKED_INVALID_EVALUATION_CORPUS,
            BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS,
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
        b in active_blockers for b in REQUIRED_HONEST_BLOCKERS_WHEN_UNREADY
    )

    # Never claim all_core_pass without real gates
    return {
        "gates": gates,
        "thresholds": thr,
        "all_core_pass": all_core,
        "terminal_status": terminal,
        "primary_terminal_status": primary_terminal,
        "active_blockers": active_blockers,
        "required_honest_blockers": list(REQUIRED_HONEST_BLOCKERS_WHEN_UNREADY),
        "required_honest_blockers_present": honest_present,
        "evaluation_level": evaluation_level,
        "ready_requirements": {
            "real_corpus_sufficient": corpus_ok,
            "label_provenance_valid": bool(
                (corpus_audit.get("dual_review") or {}).get("ok")
            )
            if corpus_audit
            else False,
            "unlabeled_match_zero": unlabeled_ok,
            "real_recall_approved": (
                ret_pass and pres_pass and power_ok and evaluation_level == "C"
            ),
            # Never approve precision on vacuous 0-MATCH or non-C
            "real_precision_approved": (
                com_pass
                and evaluation_level == "C"
                and not precision_vacuous
                and all_match_n > 0
            ),
            "real_embeddings_evaluated": emb_ok,
            "real_llm_validated": llm_ok,
            "review_capacity_within_limit": review_ok,
            "full_suite_green": suite_ok,
            "rc_v2_intact": rc_v2_intact is True,
        },
    }


def quotas_ok(corpus_audit: dict[str, Any]) -> bool:
    q = corpus_audit.get("quotas") or {}
    return bool(q.get("ok"))
