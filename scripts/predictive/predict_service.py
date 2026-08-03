"""Immutable prediction emission and honest response envelopes."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.predictive.claims import ClaimRegistry, load_registry
from scripts.predictive.models import FittedModel, explain_linear


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@dataclass
class PredictionRecord:
    prediction_id: str
    prediction_group_id: str
    version: int
    target_name: str
    claim_id: str
    claim_state: str
    as_of_at: str
    model_id: str | None
    model_version: str | None
    score: float | None
    probability: float | None
    prediction_interval: dict[str, float] | None
    quantiles: dict[str, float]
    features: dict[str, float]
    sample_support: int | None
    cohort: str | None
    horizon: str | None
    valid_until: str | None
    limitations: list[str]
    prediction_allowed: bool
    is_calibrated: bool
    explanations: dict[str, Any]
    entity_id: str | None = None
    procurement_id: str | None = None
    supplier_id: str | None = None
    mode: str = "shadow"
    vocabulary: str = "score não calibrado"
    data_freshness: str | None = None
    created_at: str = field(default_factory=lambda: _utc_now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def claim_id_for_target(target_name: str) -> str:
    if target_name.startswith("demand_"):
        return "PREDICTIVE_DEMAND_FORECAST_AVAILABLE"
    if target_name.startswith("competitive_winner"):
        return "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE"
    if target_name.startswith("competitive_participation"):
        return "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE"
    if target_name.startswith("winning_discount"):
        return "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE"
    if target_name.startswith("extra_win"):
        return "EXTRA_WIN_PROBABILITY_AVAILABLE"
    if target_name.startswith("optimal_bid"):
        return "OPTIMAL_BID_RECOMMENDATION_AVAILABLE"
    return "PREDICTIVE_MARKET_INTELLIGENCE_AVAILABLE"


def emit_prediction(
    *,
    target_name: str,
    features: dict[str, float],
    feature_names: list[str],
    model: FittedModel | None,
    model_id: str | None,
    model_version: str | None,
    registry: ClaimRegistry | None = None,
    entity_id: str | None = None,
    procurement_id: str | None = None,
    supplier_id: str | None = None,
    horizon: str | None = None,
    cohort: str | None = None,
    sample_support: int | None = None,
    as_of: datetime | None = None,
    mode: str = "shadow",
    quantiles: dict[str, float] | None = None,
    extra_limitations: list[str] | None = None,
) -> PredictionRecord:
    reg = registry or load_registry()
    claim_id = claim_id_for_target(target_name)
    claim = reg.get(claim_id)
    as_of = as_of or _utc_now()
    allowed = claim.state == "PRODUCTION_AVAILABLE"
    limitations = list(claim.limitations) + list(claim.blockers)
    if claim.state != "PRODUCTION_AVAILABLE":
        limitations.append(f"Claim {claim_id} state={claim.state}; external availability forbidden")
    if extra_limitations:
        limitations.extend(extra_limitations)

    score: float | None = None
    probability: float | None = None
    explanations: dict[str, Any] = {}
    is_calibrated = bool(model and model.calibrated)

    if model is None:
        limitations.append("No approved model loaded")
        vocabulary = "dados insuficientes"
    else:
        x = [float(features.get(k, 0.0) or 0.0) for k in feature_names]
        if model.task == "classification":
            p = float(model.predict_proba([x])[0])
            score = p
            if is_calibrated and allowed:
                probability = p
                vocabulary = "probabilidade calibrada"
            elif is_calibrated and claim.state in {
                "HISTORICAL_BACKTEST_PROVEN",
                "SHADOW_OPERATIONAL",
                "PROSPECTIVE_CALIBRATED",
            }:
                # May show as calibrated score in shadow, not commercial probability
                probability = None
                vocabulary = "score não calibrado" if not is_calibrated else "probabilidade calibrada (shadow only)"
                # For shadow we still store probability field for outcome eval but flag not allowed
                probability = p
                vocabulary = "probabilidade calibrada" if is_calibrated else "score não calibrado"
                if not allowed:
                    vocabulary = (
                        "probabilidade calibrada (uso interno/shadow; claim não PRODUCTION_AVAILABLE)"
                        if is_calibrated
                        else "score não calibrado"
                    )
            else:
                probability = None
                vocabulary = "score não calibrado"
            explanations = explain_linear(model, x)
        else:
            pred = float(model.predict([x])[0])
            score = pred
            probability = None
            vocabulary = "intervalo preditivo" if quantiles else "score não calibrado"
            explanations = explain_linear(model, x)

    if claim.state in {"SUSPENDED_DRIFT", "SUSPENDED_DATA_QUALITY", "DATA_BLOCKED"}:
        probability = None
        vocabulary = {
            "SUSPENDED_DRIFT": "modelo suspenso",
            "SUSPENDED_DATA_QUALITY": "modelo suspenso",
            "DATA_BLOCKED": "dados insuficientes",
        }.get(claim.state, "dados insuficientes")
        limitations.append(f"Prediction blocked by claim state {claim.state}")

    group = hashlib.sha256(
        f"{target_name}|{entity_id}|{procurement_id}|{supplier_id}|{as_of.isoformat()}|{horizon}".encode()
    ).hexdigest()[:20]
    pred_id = f"pred_{uuid.uuid4().hex[:16]}"
    valid_until = (as_of + timedelta(days=7)).isoformat()

    # Never set prediction_allowed unless PRODUCTION
    return PredictionRecord(
        prediction_id=pred_id,
        prediction_group_id=f"grp_{group}",
        version=1,
        target_name=target_name,
        claim_id=claim_id,
        claim_state=claim.state,
        as_of_at=as_of.isoformat(),
        model_id=model_id,
        model_version=model_version,
        score=score,
        probability=probability if (is_calibrated or mode == "shadow") else None,
        prediction_interval=None,
        quantiles=quantiles or {},
        features=dict(features),
        sample_support=sample_support,
        cohort=cohort,
        horizon=horizon,
        valid_until=valid_until,
        limitations=limitations,
        prediction_allowed=allowed and is_calibrated,
        is_calibrated=is_calibrated,
        explanations=explanations,
        entity_id=entity_id,
        procurement_id=procurement_id,
        supplier_id=supplier_id,
        mode=mode,
        vocabulary=vocabulary,
        data_freshness=as_of.isoformat(),
    )


def blocked_prediction(
    *,
    target_name: str,
    reason: str,
    registry: ClaimRegistry | None = None,
) -> PredictionRecord:
    return emit_prediction(
        target_name=target_name,
        features={},
        feature_names=[],
        model=None,
        model_id=None,
        model_version=None,
        registry=registry,
        extra_limitations=[reason],
    )
