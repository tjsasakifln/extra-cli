"""Phase 11 — statistical gates with honest insufficient-power handling."""
from __future__ import annotations

from typing import Any

from scripts.ops.hybrid_sector.evaluation.metrics import statistical_power_ok


INSUFFICIENT_STATISTICAL_POWER = "INSUFFICIENT_STATISTICAL_POWER"


def evaluate_gates(
    retrieval: dict[str, Any],
    decision: dict[str, Any],
    *,
    audit: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    thr = {
        "retrieval_recall_point": 0.995,
        "retrieval_recall_lower_95": 0.99,
        "preservation_recall_point": 0.995,
        "preservation_recall_lower_95": 0.99,
        "match_precision_point": 0.95,
        "match_precision_lower_95": 0.90,
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

    # Retrieval gate
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
    }

    # Commercial MATCH precision
    m_point = float(decision.get("match_precision") or 0)
    m_low = float(decision.get("match_precision_lower_95") or 0)
    hard_fp = int(decision.get("match_false_positives_hard") or 0)
    # Gross non-engineering FP: hard_fp among MATCH
    com_pass = (
        m_point >= thr["match_precision_point"]
        and m_low >= thr["match_precision_lower_95"]
        and hard_fp == 0
    )
    gates["commercial"] = {
        "pass": com_pass,
        "point": m_point,
        "lower_95": m_low,
        "hard_false_positives": hard_fp,
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

    all_core = (
        (ret_pass and pres_pass if power_ok else False)
        and com_pass
        and audit_pass
    )

    if not power_ok:
        terminal = "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"
    elif not ret_pass or not pres_pass:
        terminal = "BLOCKED_INSUFFICIENT_RECALL"
    elif not com_pass:
        # Commercial precision failure blocks readiness (same family of assurance block)
        terminal = "BLOCKED_INSUFFICIENT_RECALL"
    elif not audit_pass:
        terminal = "BLOCKED_LLM_OPERATIONAL_VALIDATION"
    else:
        terminal = "READY_FOR_RECALL_ASSURANCE_REVIEW"

    # Annotate commercial precision separately for honest reporting
    gates["commercial"]["blocks_readiness"] = not com_pass

    return {
        "gates": gates,
        "thresholds": thr,
        "all_core_pass": all_core,
        "terminal_status": terminal,
    }
