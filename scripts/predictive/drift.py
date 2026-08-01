"""Drift monitoring and claim suspension hooks."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts.predictive.claims import ClaimRegistry, load_registry
from scripts.predictive.metrics import brier_score, brier_skill_score, expected_calibration_error


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class DriftReport:
    drift_run_id: str
    target_name: str
    decision: str  # ok | suspend_drift | suspend_data_quality | insufficient_data
    reasons: list[str] = field(default_factory=list)
    brier: float | None = None
    brier_skill_score: float | None = None
    ece: float | None = None
    n_outcomes: int = 0
    n_positives: int = 0
    prevalence: float | None = None
    psi_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def population_stability_index(
    expected_rates: Sequence[float],
    actual_rates: Sequence[float],
    eps: float = 1e-6,
) -> float:
    """PSI between two same-length distributions (bin rates summing ~1)."""
    if len(expected_rates) != len(actual_rates) or not expected_rates:
        return float("nan")
    psi = 0.0
    for e, a in zip(expected_rates, actual_rates):
        e = max(float(e), eps)
        a = max(float(a), eps)
        psi += (a - e) * math.log(a / e)
    return float(psi)


def evaluate_outcomes_drift(
    outcomes: Sequence[dict[str, Any]],
    predictions: Sequence[dict[str, Any]],
    *,
    target_name: str,
    baseline_prevalence: float | None = None,
    ece_suspend: float = 0.10,
    require_bss_non_negative: bool = True,
    min_outcomes: int = 30,
) -> DriftReport:
    """Compute prospective/window metrics and recommend suspend or ok."""
    by_id = {p.get("prediction_id"): p for p in predictions if p.get("prediction_id")}
    y_true: list[float] = []
    y_prob: list[float] = []
    for o in outcomes:
        pred = by_id.get(o.get("prediction_id"))
        if not pred:
            continue
        if str(pred.get("target_name") or "") != target_name and target_name != "all":
            # allow filter by matching prediction target
            if target_name not in str(pred.get("target_name") or ""):
                continue
        lv = o.get("label_value")
        if lv is None:
            continue
        score = pred.get("probability")
        if score is None:
            score = pred.get("score")
        if score is None:
            continue
        try:
            y_true.append(float(lv))
            y_prob.append(float(score))
        except (TypeError, ValueError):
            continue

    reasons: list[str] = []
    n = len(y_true)
    n_pos = int(sum(1 for y in y_true if y == 1.0))
    if n < min_outcomes:
        return DriftReport(
            drift_run_id=f"drift_{uuid.uuid4().hex[:12]}",
            target_name=target_name,
            decision="insufficient_data",
            reasons=[f"n_outcomes={n} < min_outcomes={min_outcomes}"],
            n_outcomes=n,
            n_positives=n_pos,
        )

    prev = float(sum(y_true) / n)
    brier = brier_score(y_true, y_prob)
    base_p = baseline_prevalence if baseline_prevalence is not None else prev
    base_probs = [base_p] * n
    bss = brier_skill_score(y_true, y_prob, base_probs)
    ece = expected_calibration_error(y_true, y_prob)

    decision = "ok"
    if ece is not None and ece > ece_suspend:
        decision = "suspend_drift"
        reasons.append(f"ECE={ece:.4f} > {ece_suspend}")
    if require_bss_non_negative and bss is not None and bss < 0:
        decision = "suspend_drift"
        reasons.append(f"BSS={bss:.4f} < 0")
    if baseline_prevalence is not None and abs(prev - baseline_prevalence) > 0.25:
        reasons.append(
            f"prevalence shift {baseline_prevalence:.3f} -> {prev:.3f}"
        )
        if decision == "ok":
            decision = "suspend_data_quality"

    return DriftReport(
        drift_run_id=f"drift_{uuid.uuid4().hex[:12]}",
        target_name=target_name,
        decision=decision,
        reasons=reasons,
        brier=brier,
        brier_skill_score=bss,
        ece=ece,
        n_outcomes=n,
        n_positives=n_pos,
        prevalence=prev,
        psi_json={
            "baseline_prevalence": baseline_prevalence,
            "window_prevalence": prev,
        },
    )


CLAIM_FOR_TARGET = {
    "demand_30d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
    "demand_60d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
    "demand_90d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
    "competitive_winner_p2a": "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
    "winning_discount_p3": "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
}


def apply_drift_to_claims(
    report: DriftReport,
    registry: ClaimRegistry | None = None,
) -> dict[str, Any]:
    """Suspend claim when drift decision requires it."""
    reg = registry or load_registry()
    claim_id = CLAIM_FOR_TARGET.get(report.target_name)
    if not claim_id:
        return {"applied": False, "reason": "no claim mapping", "report": report.to_dict()}

    cur = reg.get(claim_id)
    if report.decision == "suspend_drift":
        if cur.state not in {"SUSPENDED_DRIFT", "NOT_IMPLEMENTED"}:
            try:
                reg.set_state(
                    claim_id,
                    "SUSPENDED_DRIFT",
                    blockers=report.reasons,
                    evidence={"drift": report.to_dict()},
                    force=True,
                )
            except ValueError as exc:
                return {"applied": False, "error": str(exc), "report": report.to_dict()}
        reg.save()
        return {"applied": True, "claim_id": claim_id, "new_state": "SUSPENDED_DRIFT"}
    if report.decision == "suspend_data_quality":
        if cur.state not in {"SUSPENDED_DATA_QUALITY", "NOT_IMPLEMENTED"}:
            try:
                reg.set_state(
                    claim_id,
                    "SUSPENDED_DATA_QUALITY",
                    blockers=report.reasons,
                    evidence={"drift": report.to_dict()},
                    force=True,
                )
            except ValueError as exc:
                return {"applied": False, "error": str(exc), "report": report.to_dict()}
        reg.save()
        return {
            "applied": True,
            "claim_id": claim_id,
            "new_state": "SUSPENDED_DATA_QUALITY",
        }
    return {
        "applied": False,
        "reason": report.decision,
        "claim_id": claim_id,
        "claim_state": cur.state,
        "report": report.to_dict(),
    }


def default_drift_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "artifacts" / "predictive" / "drift_last.json"
