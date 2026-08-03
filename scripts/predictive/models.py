"""Baselines and challenger models for predictive targets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, QuantileRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass
class FittedModel:
    name: str
    family: str
    model: Any
    feature_names: list[str]
    task: str  # classification | regression
    calibrated: bool = False
    calibration_method: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, x_mat: Sequence[Sequence[float]]) -> np.ndarray:
        arr = np.asarray(x_mat, dtype=float)
        if self.task != "classification":
            raise TypeError("predict_proba only for classification")
        if hasattr(self.model, "predict_proba"):
            proba = self.model.predict_proba(arr)
            if proba.ndim == 2 and proba.shape[1] >= 2:
                return proba[:, 1]
            return proba.ravel()
        # decision_function fallback
        if hasattr(self.model, "decision_function"):
            z = self.model.decision_function(arr)
            return 1.0 / (1.0 + np.exp(-z))
        raise TypeError(f"Model {self.name} cannot predict_proba")

    def predict(self, x_mat: Sequence[Sequence[float]]) -> np.ndarray:
        arr = np.asarray(x_mat, dtype=float)
        return np.asarray(self.model.predict(arr), dtype=float)

    def artifact_blob(self) -> bytes:
        """Lightweight serializable metadata + coef when available (not full sklearn dump)."""
        meta: dict[str, Any] = {
            "name": self.name,
            "family": self.family,
            "feature_names": self.feature_names,
            "task": self.task,
            "calibrated": self.calibrated,
            "calibration_method": self.calibration_method,
            "extras": self.extras,
        }
        # coefficients for linear models
        m = self.model
        if isinstance(m, Pipeline):
            m = m.named_steps.get("clf") or m.named_steps.get("reg") or m
        if hasattr(m, "coef_"):
            meta["coef_"] = np.asarray(m.coef_).tolist()
            if hasattr(m, "intercept_"):
                meta["intercept_"] = np.asarray(m.intercept_).tolist()
        return json.dumps(meta, sort_keys=True).encode()

    def artifact_sha256(self) -> str:
        return hashlib.sha256(self.artifact_blob()).hexdigest()


def _xy(x_mat: Sequence[Sequence[float]], y: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    return np.asarray(x_mat, dtype=float), np.asarray(y, dtype=float)


# ---- Classification baselines ----


def fit_prevalence_baseline(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
) -> FittedModel:
    prev = float(np.mean(y)) if len(y) else 0.5

    class _Prev:
        def __init__(self, p: float) -> None:
            self.p = p

        def predict_proba(self, x_mat: np.ndarray) -> np.ndarray:
            n = len(x_mat)
            return np.column_stack([np.full(n, 1 - self.p), np.full(n, self.p)])

    return FittedModel(
        name="prevalence_baseline",
        family="baseline",
        model=_Prev(prev),
        feature_names=feature_names,
        task="classification",
        extras={"prevalence": prev},
    )


def fit_frequency_feature_baseline(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
    feature_key: str = "n_contracts_365d",
) -> FittedModel:
    """Map a single frequency feature to empirical rate via binning."""
    arr, yy = _xy(x_mat, y)
    if feature_key in feature_names:
        idx = feature_names.index(feature_key)
    else:
        idx = 0
    col = arr[:, idx] if arr.size else np.array([])
    # simple monotone: p = sigmoid(a * log1p(x) + b) fit via logistic on one feature
    x1 = np.log1p(np.maximum(col, 0)).reshape(-1, 1)
    if len(yy) < 10 or len(np.unique(yy)) < 2:
        return fit_prevalence_baseline(x_mat, y, feature_names)
    clf = LogisticRegression(max_iter=500, C=1.0)
    clf.fit(x1, yy)

    class _Wrap:
        def __init__(self, clf: Any, idx: int) -> None:
            self.clf = clf
            self.idx = idx

        def predict_proba(self, x_mat: np.ndarray) -> np.ndarray:
            x1 = np.log1p(np.maximum(x_mat[:, self.idx], 0)).reshape(-1, 1)
            return self.clf.predict_proba(x1)

    return FittedModel(
        name="frequency_baseline",
        family="baseline",
        model=_Wrap(clf, idx),
        feature_names=feature_names,
        task="classification",
        extras={"feature_key": feature_key},
    )


def fit_logistic(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
    *,
    c_reg: float = 1.0,
) -> FittedModel:
    arr, yy = _xy(x_mat, y)
    if len(yy) < 10 or len(np.unique(yy)) < 2:
        return fit_prevalence_baseline(x_mat, y, feature_names)
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(max_iter=1000, C=c_reg, class_weight="balanced"),
            ),
        ]
    )
    pipe.fit(arr, yy)
    return FittedModel(
        name="logistic_l2",
        family="logistic",
        model=pipe,
        feature_names=feature_names,
        task="classification",
    )


def fit_hist_gbm_classifier(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
    *,
    max_depth: int = 4,
    max_iter: int = 100,
) -> FittedModel:
    arr, yy = _xy(x_mat, y)
    if len(yy) < 50 or len(np.unique(yy)) < 2:
        return fit_logistic(x_mat, y, feature_names)
    clf = HistGradientBoostingClassifier(
        max_depth=max_depth,
        max_iter=max_iter,
        learning_rate=0.08,
        random_state=42,
    )
    clf.fit(arr, yy)
    return FittedModel(
        name="hist_gbm_clf",
        family="hist_gbm",
        model=clf,
        feature_names=feature_names,
        task="classification",
    )


def calibrate_classifier(
    fitted: FittedModel,
    x_cal: Sequence[Sequence[float]],
    y_cal: Sequence[float],
    method: str = "isotonic",
) -> FittedModel:
    """Calibrate on held-out set. method: isotonic | sigmoid (Platt)."""
    arr, yy = _xy(x_cal, y_cal)
    if len(yy) < 30 or len(np.unique(yy)) < 2:
        return fitted
    # sklearn CalibratedClassifierCV with cv='prefit' deprecated; use frozen estimator
    try:
        from sklearn.frozen import FrozenEstimator

        base = FrozenEstimator(fitted.model)
        cal = CalibratedClassifierCV(base, method=method, cv=None)
    except Exception:
        # fallback: fit new calibrator via logistic on scores
        scores = fitted.predict_proba(arr).reshape(-1, 1)
        cal_lr = LogisticRegression(max_iter=500)
        cal_lr.fit(scores, yy)

        class _Platt:
            def __init__(self, base: FittedModel, lr: Any) -> None:
                self.base = base
                self.lr = lr

            def predict_proba(self, x_mat: np.ndarray) -> np.ndarray:
                s = self.base.predict_proba(x_mat).reshape(-1, 1)
                return self.lr.predict_proba(s)

        return FittedModel(
            name=f"{fitted.name}_calibrated_platt",
            family=fitted.family,
            model=_Platt(fitted, cal_lr),
            feature_names=fitted.feature_names,
            task="classification",
            calibrated=True,
            calibration_method="sigmoid",
            extras=dict(fitted.extras),
        )

    cal.fit(arr, yy)
    return FittedModel(
        name=f"{fitted.name}_calibrated_{method}",
        family=fitted.family,
        model=cal,
        feature_names=fitted.feature_names,
        task="classification",
        calibrated=True,
        calibration_method=method,
        extras=dict(fitted.extras),
    )


# ---- Regression / quantiles ----


def fit_median_baseline(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
) -> FittedModel:
    med = float(np.median(y)) if len(y) else 0.0

    class _Med:
        def __init__(self, m: float) -> None:
            self.m = m

        def predict(self, x_mat: np.ndarray) -> np.ndarray:
            return np.full(len(x_mat), self.m)

    return FittedModel(
        name="median_baseline",
        family="baseline",
        model=_Med(med),
        feature_names=feature_names,
        task="regression",
        extras={"median": med},
    )


def fit_quantile_regressor(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
    quantile: float = 0.5,
) -> FittedModel:
    arr, yy = _xy(x_mat, y)
    if len(yy) < 20:
        return fit_median_baseline(x_mat, y, feature_names)
    try:
        reg = QuantileRegressor(quantile=quantile, alpha=0.1, solver="highs")
        reg.fit(arr, yy)
    except Exception:
        return fit_median_baseline(x_mat, y, feature_names)
    return FittedModel(
        name=f"quantile_reg_{quantile}",
        family="quantile",
        model=reg,
        feature_names=feature_names,
        task="regression",
        extras={"quantile": quantile},
    )


def fit_hist_gbm_regressor(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
) -> FittedModel:
    arr, yy = _xy(x_mat, y)
    if len(yy) < 50:
        return fit_median_baseline(x_mat, y, feature_names)
    reg = HistGradientBoostingRegressor(max_depth=4, max_iter=100, learning_rate=0.08, random_state=42)
    reg.fit(arr, yy)
    return FittedModel(
        name="hist_gbm_reg",
        family="hist_gbm",
        model=reg,
        feature_names=feature_names,
        task="regression",
    )


def fit_quantile_bundle(
    x_mat: Sequence[Sequence[float]],
    y: Sequence[float],
    feature_names: list[str],
) -> dict[str, FittedModel]:
    return {
        "p10": fit_quantile_regressor(x_mat, y, feature_names, 0.1),
        "p50": fit_quantile_regressor(x_mat, y, feature_names, 0.5),
        "p90": fit_quantile_regressor(x_mat, y, feature_names, 0.9),
    }


def explain_linear(fitted: FittedModel, x_row: Sequence[float], top_k: int = 5) -> dict[str, list[dict[str, float]]]:
    """Coefficient × value decomposition for logistic/linear pipelines."""
    m = fitted.model
    coef = None
    intercept = 0.0
    x = np.asarray(x_row, dtype=float)
    if isinstance(m, Pipeline):
        scaler = m.named_steps.get("scaler")
        clf = m.named_steps.get("clf") or m.named_steps.get("reg")
        if scaler is not None:
            x = scaler.transform(x.reshape(1, -1))[0]
        if clf is not None and hasattr(clf, "coef_"):
            coef = np.asarray(clf.coef_).ravel()
            intercept = float(np.asarray(clf.intercept_).ravel()[0])
    elif hasattr(m, "coef_"):
        coef = np.asarray(m.coef_).ravel()
        intercept = float(np.asarray(m.intercept_).ravel()[0]) if hasattr(m, "intercept_") else 0.0

    if coef is None:
        return {"factors_up": [], "factors_down": [], "method": "unavailable"}

    contribs = []
    for name, c, xv in zip(fitted.feature_names, coef, x):
        contribs.append({"feature": name, "contribution": float(c * xv), "value": float(xv)})
    contribs.sort(key=lambda d: d["contribution"], reverse=True)
    up = [c for c in contribs if c["contribution"] > 0][:top_k]
    down = [c for c in contribs if c["contribution"] < 0][-top_k:]
    down = list(reversed(down))
    return {
        "factors_up": up,
        "factors_down": down,
        "intercept": intercept,
        "method": "coefficient_decomposition",
    }
