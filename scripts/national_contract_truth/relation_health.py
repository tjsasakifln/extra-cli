"""#316 — per-relation autovacuum / analyze / bloat gate.

Thresholds are named and versioned. A relation that would wrap around,
bloat past the ratio, or serve stale statistics is ALERT/BLOCK.
This module does not claim VPS soak or hardcoded host sizes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

POLICY_VERSION = "relation-health-v1"
NATIONAL_RELATIONS: tuple[str, ...] = ("pncp_supplier_contracts",)

HealthLevel = Literal["OK", "ALERT", "BLOCK"]


@dataclass(frozen=True)
class RelationThresholds:
    dead_ratio: float
    analyze_age: timedelta
    vacuum_age: timedelta
    freeze_age_alert: int
    wraparound_block: int


DEFAULT_THRESHOLDS = RelationThresholds(
    dead_ratio=0.20,
    analyze_age=timedelta(hours=24),
    vacuum_age=timedelta(days=7),
    freeze_age_alert=500_000_000,
    wraparound_block=1_500_000_000,
)


@dataclass(frozen=True)
class RelationMetrics:
    relation: str
    dead_ratio: float
    last_analyze_age: timedelta | None
    last_vacuum_age: timedelta | None
    freeze_age: int
    heap_bytes: int
    index_bytes: int


@dataclass(frozen=True)
class RelationHealth:
    relation: str
    level: HealthLevel
    reasons: tuple[str, ...]
    should_analyze: bool
    policy_version: str = POLICY_VERSION


def evaluate_relation(
    metrics: RelationMetrics,
    *,
    thresholds: RelationThresholds = DEFAULT_THRESHOLDS,
) -> RelationHealth:
    reasons: list[str] = []
    level: HealthLevel = "OK"
    if metrics.freeze_age >= thresholds.wraparound_block:
        reasons.append("wraparound_imminent")
        level = "BLOCK"
    elif metrics.freeze_age >= thresholds.freeze_age_alert:
        reasons.append("freeze_age_high")
        level = "ALERT"
    if metrics.dead_ratio >= thresholds.dead_ratio:
        reasons.append("dead_ratio_high")
        if level != "BLOCK":
            level = "ALERT"
    if metrics.last_analyze_age is None or metrics.last_analyze_age > thresholds.analyze_age:
        reasons.append("analyze_stale")
        if level != "BLOCK":
            level = "ALERT"
    if metrics.last_vacuum_age is None or metrics.last_vacuum_age > thresholds.vacuum_age:
        reasons.append("vacuum_stale")
        if level != "BLOCK":
            level = "ALERT"
    return RelationHealth(
        relation=metrics.relation,
        level=level,
        reasons=tuple(reasons),
        should_analyze="analyze_stale" in reasons or "dead_ratio_high" in reasons,
    )


def analyze_after_bulk_load(*, committed: bool, reconciled: bool) -> bool:
    """Bulk load may trigger ANALYZE only after commit and reconciliation."""
    return committed and reconciled
