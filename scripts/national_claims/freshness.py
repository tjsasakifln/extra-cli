"""Freshness overlay. A breach yields STALE and never authorizes the current claim."""

from __future__ import annotations

from datetime import timedelta

from scripts.national_claims.models import FreshnessInput
from scripts.national_contract_truth.freshness_slo import (
    LayerObservation,
    evaluate_layer,
)

FRESHNESS_OK = "OK"
FRESHNESS_STALE = "STALE"


def evaluate_freshness(observation: FreshnessInput) -> tuple[str, str]:
    """Return (status, reason). status is OK or STALE."""
    layer = observation.layer if observation.layer in {"publication", "correction", "anti_entropy"} else "publication"
    result = evaluate_layer(
        LayerObservation(
            layer=layer,  # type: ignore[arg-type]
            age_since_complete_run=timedelta(hours=float(observation.age_hours)),
            lag_p50=timedelta(hours=float(observation.lag_p99_hours)),
            lag_p95=timedelta(hours=float(observation.lag_p99_hours)),
            lag_p99=timedelta(hours=float(observation.lag_p99_hours)),
        )
    )
    if result.status == "BREACH":
        return FRESHNESS_STALE, result.reason
    return FRESHNESS_OK, result.reason
