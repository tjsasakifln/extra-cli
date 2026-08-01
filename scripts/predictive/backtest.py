"""Rolling-origin / walk-forward validation. Random split is forbidden as primary."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Sequence

import numpy as np

from scripts.predictive.dataset import examples_to_matrix
from scripts.predictive.metrics import (
    classification_report,
    evaluate_classification_gates,
    regression_report,
)
from scripts.predictive.models import (
    FittedModel,
    calibrate_classifier,
    fit_frequency_feature_baseline,
    fit_hist_gbm_classifier,
    fit_hist_gbm_regressor,
    fit_logistic,
    fit_median_baseline,
    fit_prevalence_baseline,
    fit_quantile_bundle,
)


@dataclass
class FoldSpec:
    fold_id: str
    train_end: datetime
    val_end: datetime
    test_end: datetime


@dataclass
class BacktestResult:
    target_name: str
    task: str
    folds: list[dict[str, Any]] = field(default_factory=list)
    holdout: dict[str, Any] = field(default_factory=dict)
    best_model: str | None = None
    best_metrics: dict[str, Any] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    baselines: dict[str, Any] = field(default_factory=dict)
    claim_recommendation: str = "DATA_BLOCKED"
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_time_folds(
    as_ofs: Sequence[datetime],
    n_folds: int = 3,
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return list of (train_idx, cal_idx, test_idx) by time order.

    Splits unique sorted times into expanding train, then cal, then test.
    """
    order = np.argsort([a.timestamp() for a in as_ofs])
    n = len(order)
    if n < 50:
        # single fold if tiny
        cut1 = int(n * 0.6)
        cut2 = int(n * 0.8)
        return [
            (order[:cut1], order[cut1:cut2], order[cut2:]),
        ]

    # Use quantiles of time for fold boundaries
    folds: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    # Expanding window: for k in 1..n_folds
    # train: 0 .. t_k, cal: t_k..t_k+gap, test: next segment
    qs = np.linspace(0.4, 0.85, n_folds)
    for i, q in enumerate(qs):
        train_end = int(n * q)
        cal_end = int(n * min(q + 0.08, 0.92))
        test_end = int(n * min(q + 0.16, 1.0))
        if i == n_folds - 1:
            test_end = n
        tr = order[:train_end]
        ca = order[train_end:cal_end]
        te = order[cal_end:test_end]
        if len(tr) < 20 or len(te) < 10:
            continue
        folds.append((tr, ca, te))
    if not folds:
        cut1 = int(n * 0.6)
        cut2 = int(n * 0.8)
        folds = [(order[:cut1], order[cut1:cut2], order[cut2:])]
    return folds


def _subset(
    X: list[list[float]], y: list[float], idx: np.ndarray
) -> tuple[list[list[float]], list[float]]:
    return [X[i] for i in idx], [y[i] for i in idx]


def run_classification_backtest(
    examples: Sequence[dict[str, Any]],
    *,
    target_name: str,
    n_folds: int = 3,
) -> BacktestResult:
    if not examples:
        return BacktestResult(
            target_name=target_name,
            task="classification",
            claim_recommendation="DATA_BLOCKED",
            blockers=["No examples"],
            gate={"passed": False, "data_blocked": True, "reasons": ["empty"]},
        )

    feature_names, X, y, as_ofs = examples_to_matrix(examples)
    folds_idx = make_time_folds(as_ofs, n_folds=n_folds)
    fold_rows: list[dict[str, Any]] = []

    # Collect holdout = last fold test
    last_test_metrics: dict[str, Any] = {}
    model_scores: dict[str, list[float]] = {
        "prevalence_baseline": [],
        "frequency_baseline": [],
        "logistic_l2": [],
        "hist_gbm_clf": [],
    }

    for fi, (tr, ca, te) in enumerate(folds_idx):
        Xtr, ytr = _subset(X, y, tr)
        Xca, yca = _subset(X, y, ca) if len(ca) else (Xtr[-max(1, len(Xtr)//5):], ytr[-max(1, len(ytr)//5):])
        Xte, yte = _subset(X, y, te)

        models: dict[str, FittedModel] = {
            "prevalence_baseline": fit_prevalence_baseline(Xtr, ytr, feature_names),
            "frequency_baseline": fit_frequency_feature_baseline(
                Xtr, ytr, feature_names
            ),
            "logistic_l2": fit_logistic(Xtr, ytr, feature_names),
            "hist_gbm_clf": fit_hist_gbm_classifier(Xtr, ytr, feature_names),
        }
        # calibrate logistic and gbm on cal set
        for name in ("logistic_l2", "hist_gbm_clf"):
            models[name] = calibrate_classifier(
                models[name], Xca, yca, method="sigmoid"
            )

        fold_metrics: dict[str, Any] = {"fold_id": f"fold_{fi}", "n_train": len(ytr), "n_test": len(yte)}
        base_proba = models["prevalence_baseline"].predict_proba(Xte)
        # choose best baseline among prevalence and frequency by brier
        from scripts.predictive.metrics import brier_score

        freq_proba = models["frequency_baseline"].predict_proba(Xte)
        if brier_score(yte, freq_proba) < brier_score(yte, base_proba):
            best_base = freq_proba
            best_base_name = "frequency_baseline"
        else:
            best_base = base_proba
            best_base_name = "prevalence_baseline"

        for name, model in models.items():
            proba = model.predict_proba(Xte)
            rep = classification_report(yte, proba, baseline_prob=best_base)
            rep["baseline_name"] = best_base_name
            rep["calibrated"] = model.calibrated
            fold_metrics[name] = rep
            if name in model_scores:
                # primary metric: BSS
                model_scores[name].append(float(rep.get("brier_skill_score") or -1))

        fold_rows.append(fold_metrics)
        last_test_metrics = fold_metrics

    # Holdout = last fold
    best_model = max(
        model_scores.keys(),
        key=lambda k: float(np.mean(model_scores[k])) if model_scores[k] else -999,
    )
    best_fold_metrics = last_test_metrics.get(best_model) or {}
    # gate vs best baseline
    gate = evaluate_classification_gates(best_fold_metrics)

    claim = "BACKTEST_FAILED"
    blockers: list[str] = list(gate.get("reasons") or [])
    if gate.get("data_blocked"):
        claim = "DATA_BLOCKED"
    elif gate.get("passed"):
        claim = "HISTORICAL_BACKTEST_PROVEN"
    else:
        claim = "BACKTEST_FAILED"

    return BacktestResult(
        target_name=target_name,
        task="classification",
        folds=fold_rows,
        holdout=last_test_metrics,
        best_model=best_model,
        best_metrics=best_fold_metrics,
        gate=gate,
        baselines={
            "prevalence": last_test_metrics.get("prevalence_baseline"),
            "frequency": last_test_metrics.get("frequency_baseline"),
        },
        claim_recommendation=claim,
        blockers=blockers,
    )


def run_regression_backtest(
    examples: Sequence[dict[str, Any]],
    *,
    target_name: str,
    n_folds: int = 3,
) -> BacktestResult:
    if not examples:
        return BacktestResult(
            target_name=target_name,
            task="regression",
            claim_recommendation="DATA_BLOCKED",
            blockers=["No valid discount examples"],
            gate={"passed": False, "data_blocked": True, "reasons": ["empty"]},
        )

    feature_names, X, y, as_ofs = examples_to_matrix(examples)
    folds_idx = make_time_folds(as_ofs, n_folds=n_folds)
    fold_rows: list[dict[str, Any]] = []
    last: dict[str, Any] = {}

    for fi, (tr, ca, te) in enumerate(folds_idx):
        Xtr, ytr = _subset(X, y, tr)
        Xte, yte = _subset(X, y, te)
        base = fit_median_baseline(Xtr, ytr, feature_names)
        bundle = fit_quantile_bundle(Xtr, ytr, feature_names)
        gbm = fit_hist_gbm_regressor(Xtr, ytr, feature_names)
        y_base = base.predict(Xte)
        y_p10 = bundle["p10"].predict(Xte)
        y_p50 = bundle["p50"].predict(Xte)
        y_p90 = bundle["p90"].predict(Xte)
        y_gbm = gbm.predict(Xte)
        rep_q = regression_report(
            yte, y_p50, y_p10, y_p90, baseline_p50=y_base
        )
        rep_g = regression_report(yte, y_gbm, baseline_p50=y_base)
        fold_rows.append(
            {
                "fold_id": f"fold_{fi}",
                "n_train": len(ytr),
                "n_test": len(yte),
                "quantile_bundle": rep_q,
                "hist_gbm_reg": rep_g,
                "median_baseline": regression_report(yte, y_base),
            }
        )
        last = fold_rows[-1]

    # Gate: n>=1000, pinball 10% better, MAE 5% better, coverage 75-85% for 80% interval
    q = last.get("quantile_bundle") or {}
    reasons: list[str] = []
    n = int(q.get("n") or 0)
    if n < 1000:
        reasons.append(f"n={n} < 1000")
    pinball = q.get("pinball_p50")
    pinball_b = q.get("pinball_p50_baseline")
    if pinball is None or pinball_b is None or pinball_b <= 0:
        reasons.append("missing pinball")
    elif (1 - pinball / pinball_b) < 0.10:
        reasons.append("pinball improvement < 10%")
    mae_imp = q.get("mae_improvement")
    if mae_imp is None or mae_imp < 0.05:
        reasons.append("MAE improvement < 5%")
    cov = q.get("coverage")
    if cov is None or not (0.75 <= cov <= 0.85):
        reasons.append(f"80% interval coverage={cov} not in [0.75, 0.85]")

    data_blocked = n < 1000
    passed = len(reasons) == 0
    if data_blocked:
        claim = "DATA_BLOCKED"
    elif passed:
        claim = "HISTORICAL_BACKTEST_PROVEN"
    else:
        claim = "BACKTEST_FAILED"

    return BacktestResult(
        target_name=target_name,
        task="regression",
        folds=fold_rows,
        holdout=last,
        best_model="quantile_bundle",
        best_metrics=q,
        gate={"passed": passed, "data_blocked": data_blocked, "reasons": reasons},
        baselines={"median": last.get("median_baseline")},
        claim_recommendation=claim,
        blockers=reasons,
    )


def train_production_candidate(
    examples: Sequence[dict[str, Any]],
    *,
    task: str = "classification",
) -> tuple[FittedModel, list[str], dict[str, Any]]:
    """Train final candidate on all but last 15% time (for shadow deployment)."""
    feature_names, X, y, as_ofs = examples_to_matrix(examples)
    order = np.argsort([a.timestamp() for a in as_ofs])
    n = len(order)
    cut = int(n * 0.85)
    cal_cut = int(n * 0.75)
    tr = order[:cal_cut]
    ca = order[cal_cut:cut]
    Xtr, ytr = _subset(X, y, tr)
    Xca, yca = _subset(X, y, ca) if len(ca) else (Xtr, ytr)
    if task == "classification":
        model = fit_hist_gbm_classifier(Xtr, ytr, feature_names)
        model = calibrate_classifier(model, Xca, yca, method="sigmoid")
        return model, feature_names, {"n_train": len(ytr), "n_cal": len(yca)}
    model = fit_hist_gbm_regressor(Xtr, ytr, feature_names)
    return model, feature_names, {"n_train": len(ytr)}
