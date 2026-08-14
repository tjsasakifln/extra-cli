"""#318 — national contracts freshness SLO, independent of the 1.093 entity SLAs.

A national breach blocks freshness-dependent claims. It never rewrites or
masks per-entity SLAs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

POLICY_VERSION = "contracts-freshness-slo-v1"
SloLayer = Literal["publication", "correction", "anti_entropy"]
SloStatus = Literal["OK", "BREACH"]


@dataclass(frozen=True)
class LayerSLO:
    layer: SloLayer
    max_age: timedelta


DEFAULT_SLOS: dict[SloLayer, LayerSLO] = {
    "publication": LayerSLO("publication", timedelta(hours=48)),
    "correction": LayerSLO("correction", timedelta(hours=72)),
    "anti_entropy": LayerSLO("anti_entropy", timedelta(days=30)),
}


@dataclass(frozen=True)
class LayerObservation:
    layer: SloLayer
    age_since_complete_run: timedelta
    lag_p50: timedelta
    lag_p95: timedelta
    lag_p99: timedelta


@dataclass(frozen=True)
class SloEvaluation:
    layer: SloLayer
    status: SloStatus
    reason: str
    policy_version: str = POLICY_VERSION


def evaluate_layer(obs: LayerObservation, slo: LayerSLO | None = None) -> SloEvaluation:
    target = slo or DEFAULT_SLOS[obs.layer]
    if obs.age_since_complete_run > target.max_age:
        return SloEvaluation(obs.layer, "BREACH", "complete_run_too_old")
    if obs.lag_p99 > target.max_age:
        return SloEvaluation(obs.layer, "BREACH", "source_to_first_seen_p99")
    return SloEvaluation(obs.layer, "OK", "within_slo")


def freshness_claim_allowed(
    national: list[SloEvaluation],
    *,
    entity_sla_ok: bool,
) -> bool:
    """National breach blocks the claim. Entity SLA is observed, never overwritten."""
    if any(item.status == "BREACH" for item in national):
        return False
    return entity_sla_ok


def overlay_entity_sla(national_status: SloStatus, entity_sla_status: str) -> str:
    """Return the entity SLA unchanged — national SLO must not mask it."""
    del national_status
    return entity_sla_status
