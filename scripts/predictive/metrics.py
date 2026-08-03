"""Classification and regression metrics for predictive backtests."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np


def _as_np(a: Sequence[float]) -> np.ndarray:
    return np.asarray(list(a), dtype=float)


def brier_score(y_true: Sequence[float], y_prob: Sequence[float]) -> float:
    y = _as_np(y_true)
    p = np.clip(_as_np(y_prob), 1e-15, 1 - 1e-15)
    return float(np.mean((p - y) ** 2))


def brier_skill_score(
    y_true: Sequence[float],
    y_prob: Sequence[float],
    baseline_prob: Sequence[float],
) -> float:
    bs = brier_score(y_true, y_prob)
    bs_ref = brier_score(y_true, baseline_prob)
    if bs_ref <= 1e-15:
        return 0.0 if bs <= 1e-15 else -1.0
    return float(1.0 - bs / bs_ref)


def log_loss(y_true: Sequence[float], y_prob: Sequence[float]) -> float:
    y = _as_np(y_true)
    p = np.clip(_as_np(y_prob), 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(
    y_true: Sequence[float],
    y_prob: Sequence[float],
    n_bins: int = 10,
) -> float:
    y = _as_np(y_true)
    p = _as_np(y_prob)
    if len(y) == 0:
        return 1.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (p >= lo) & (p < hi if i < n_bins - 1 else p <= hi)
        if not np.any(mask):
            continue
        conf = float(np.mean(p[mask]))
        acc = float(np.mean(y[mask]))
        ece += (np.sum(mask) / len(y)) * abs(acc - conf)
    return float(ece)


def reliability_table(
    y_true: Sequence[float],
    y_prob: Sequence[float],
    n_bins: int = 10,
) -> list[dict[str, float]]:
    y = _as_np(y_true)
    p = _as_np(y_prob)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, float]] = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (p >= lo) & (p < hi if i < n_bins - 1 else p <= hi)
        n = int(np.sum(mask))
        rows.append(
            {
                "bin_lo": float(lo),
                "bin_hi": float(hi),
                "n": float(n),
                "mean_pred": float(np.mean(p[mask])) if n else float("nan"),
                "mean_obs": float(np.mean(y[mask])) if n else float("nan"),
            }
        )
    return rows


def roc_auc(y_true: Sequence[float], y_score: Sequence[float]) -> float:
    y = _as_np(y_true)
    s = _as_np(y_score)
    pos = s[y == 1]
    neg = s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    # Mann-Whitney
    correct = 0.0
    for p in pos:
        correct += float(np.sum(p > neg)) + 0.5 * float(np.sum(p == neg))
    return float(correct / (len(pos) * len(neg)))


def average_precision(y_true: Sequence[float], y_score: Sequence[float]) -> float:
    y = _as_np(y_true)
    s = _as_np(y_score)
    order = np.argsort(-s)
    y_sorted = y[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    precision = tp / np.maximum(tp + fp, 1e-15)
    recall = tp / max(float(np.sum(y)), 1e-15)
    # AP as Riemann sum
    recall_prev = 0.0
    ap = 0.0
    for p, r in zip(precision, recall):
        ap += float(p) * float(r - recall_prev)
        recall_prev = float(r)
    return float(ap)


def precision_recall_at_threshold(
    y_true: Sequence[float], y_prob: Sequence[float], threshold: float = 0.5
) -> dict[str, float]:
    y = _as_np(y_true)
    pred = (_as_np(y_prob) >= threshold).astype(float)
    tp = float(np.sum((pred == 1) & (y == 1)))
    fp = float(np.sum((pred == 1) & (y == 0)))
    fn = float(np.sum((pred == 0) & (y == 1)))
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def lift_at_fraction(y_true: Sequence[float], y_score: Sequence[float], fraction: float = 0.1) -> float:
    y = _as_np(y_true)
    s = _as_np(y_score)
    n = len(y)
    if n == 0:
        return float("nan")
    k = max(1, int(math.ceil(fraction * n)))
    order = np.argsort(-s)[:k]
    base = float(np.mean(y))
    if base <= 0:
        return float("nan")
    return float(np.mean(y[order]) / base)


def classification_report(
    y_true: Sequence[float],
    y_prob: Sequence[float],
    baseline_prob: Sequence[float] | None = None,
) -> dict[str, Any]:
    y = _as_np(y_true)
    p = _as_np(y_prob)
    if baseline_prob is None:
        base = np.full_like(p, float(np.mean(y)) if len(y) else 0.5)
    else:
        base = _as_np(baseline_prob)
    pr = precision_recall_at_threshold(y, p, 0.5)
    return {
        "n": int(len(y)),
        "n_positives": int(np.sum(y == 1)),
        "prevalence": float(np.mean(y)) if len(y) else 0.0,
        "brier": brier_score(y, p),
        "brier_baseline": brier_score(y, base),
        "brier_skill_score": brier_skill_score(y, p, base),
        "log_loss": log_loss(y, p),
        "log_loss_baseline": log_loss(y, base),
        "ece": expected_calibration_error(y, p),
        "roc_auc": roc_auc(y, p),
        "pr_auc": average_precision(y, p),
        "lift_top5": lift_at_fraction(y, p, 0.05),
        "lift_top10": lift_at_fraction(y, p, 0.10),
        "lift_top20": lift_at_fraction(y, p, 0.20),
        **pr,
        "reliability": reliability_table(y, p),
    }


def mae(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    return float(np.mean(np.abs(_as_np(y_true) - _as_np(y_pred))))


def rmse(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    return float(np.sqrt(np.mean((_as_np(y_true) - _as_np(y_pred)) ** 2)))


def pinball_loss(y_true: Sequence[float], y_pred: Sequence[float], quantile: float) -> float:
    y = _as_np(y_true)
    q = _as_np(y_pred)
    e = y - q
    return float(np.mean(np.maximum(quantile * e, (quantile - 1) * e)))


def interval_coverage(y_true: Sequence[float], lo: Sequence[float], hi: Sequence[float]) -> dict[str, float]:
    y = _as_np(y_true)
    a = _as_np(lo)
    b = _as_np(hi)
    inside = (y >= a) & (y <= b)
    return {
        "coverage": float(np.mean(inside)) if len(y) else float("nan"),
        "mean_width": float(np.mean(b - a)) if len(y) else float("nan"),
    }


def regression_report(
    y_true: Sequence[float],
    y_p50: Sequence[float],
    y_p10: Sequence[float] | None = None,
    y_p90: Sequence[float] | None = None,
    baseline_p50: Sequence[float] | None = None,
) -> dict[str, Any]:
    y = _as_np(y_true)
    p50 = _as_np(y_p50)
    out: dict[str, Any] = {
        "n": int(len(y)),
        "mae": mae(y, p50),
        "rmse": rmse(y, p50),
        "median_ae": float(np.median(np.abs(y - p50))) if len(y) else float("nan"),
        "pinball_p50": pinball_loss(y, p50, 0.5),
    }
    if baseline_p50 is not None:
        b = _as_np(baseline_p50)
        out["mae_baseline"] = mae(y, b)
        out["pinball_p50_baseline"] = pinball_loss(y, b, 0.5)
        out["mae_improvement"] = (
            (out["mae_baseline"] - out["mae"]) / out["mae_baseline"] if out["mae_baseline"] else 0.0
        )
    if y_p10 is not None and y_p90 is not None:
        out["pinball_p10"] = pinball_loss(y, y_p10, 0.1)
        out["pinball_p90"] = pinball_loss(y, y_p90, 0.9)
        out.update(interval_coverage(y, y_p10, y_p90))
    return out


# ---- Gates from campaign (not optimizers) ----

MIN_TEST_N = 1000
MIN_TEST_POSITIVES = 100
MIN_BSS = 0.10
MIN_LOGLOSS_IMPROVEMENT = 0.05
MAX_ECE = 0.05
MIN_LIFT_TOP10 = 1.50


def evaluate_classification_gates(metrics: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    n = int(metrics.get("n") or 0)
    n_pos = int(metrics.get("n_positives") or 0)
    if n < MIN_TEST_N:
        reasons.append(f"n={n} < {MIN_TEST_N}")
    if n_pos < MIN_TEST_POSITIVES:
        reasons.append(f"n_positives={n_pos} < {MIN_TEST_POSITIVES}")
    bss = metrics.get("brier_skill_score")
    if bss is None or bss < MIN_BSS:
        reasons.append(f"BSS={bss} < {MIN_BSS}")
    ll = metrics.get("log_loss")
    ll_b = metrics.get("log_loss_baseline")
    if ll is None or ll_b is None or ll_b <= 0 or (1 - ll / ll_b) < MIN_LOGLOSS_IMPROVEMENT:
        reasons.append("log_loss improvement < 5% vs baseline")
    ece = metrics.get("ece")
    if ece is None or ece > MAX_ECE:
        reasons.append(f"ECE={ece} > {MAX_ECE}")
    lift = metrics.get("lift_top10")
    if lift is None or (isinstance(lift, float) and math.isnan(lift)) or lift < MIN_LIFT_TOP10:
        reasons.append(f"lift_top10={lift} < {MIN_LIFT_TOP10}")
    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "data_blocked": n < MIN_TEST_N or n_pos < MIN_TEST_POSITIVES,
    }
