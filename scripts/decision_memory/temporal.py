"""Temporal integrity classification — never falsify order in backfills."""

from __future__ import annotations

from datetime import datetime

from scripts.decision_memory.models import TemporalIntegrity


def _as_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive as UTC but mark order unknown when compared across sources
        return dt
    return dt


def classify_decision_temporal(
    *,
    decided_at: datetime,
    first_outcome_at: datetime | None,
    is_backfill: bool,
    order_provable: bool = True,
) -> TemporalIntegrity:
    if is_backfill and not order_provable:
        return TemporalIntegrity.HISTORICAL_UNVERIFIED
    if not order_provable:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    if first_outcome_at is None:
        return TemporalIntegrity.PROSPECTIVE
    d = _as_utc_aware(decided_at)
    o = _as_utc_aware(first_outcome_at)
    if d is None or o is None:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    # Strip tz for pure ordering if both naive/aware mixed
    if d.tzinfo is None and o.tzinfo is not None:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    if o.tzinfo is None and d.tzinfo is not None:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    if d <= o:
        return TemporalIntegrity.PROSPECTIVE
    # Decision recorded after outcome existed
    return TemporalIntegrity.HISTORICAL_UNVERIFIED


def classify_outcome_temporal(
    *,
    observed_at: datetime,
    prior_decision_at: datetime | None,
    is_backfill: bool,
    order_provable: bool = True,
) -> TemporalIntegrity:
    if prior_decision_at is None:
        return TemporalIntegrity.OUTCOME_WITHOUT_PRIOR_DECISION
    if is_backfill and not order_provable:
        return TemporalIntegrity.HISTORICAL_UNVERIFIED
    if not order_provable:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    d = _as_utc_aware(prior_decision_at)
    o = _as_utc_aware(observed_at)
    if d is None or o is None:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    if d.tzinfo is None and o.tzinfo is not None:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    if o.tzinfo is None and d.tzinfo is not None:
        return TemporalIntegrity.TEMPORAL_ORDER_UNKNOWN
    if d <= o:
        return TemporalIntegrity.PROSPECTIVE
    return TemporalIntegrity.HISTORICAL_UNVERIFIED


def is_strong_prospective(state: TemporalIntegrity) -> bool:
    """Only PROSPECTIVE may feed future strong prospective metrics."""
    return state is TemporalIntegrity.PROSPECTIVE
