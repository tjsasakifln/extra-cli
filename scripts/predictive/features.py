"""Point-in-time feature builders. All features must satisfy event_at <= as_of_at."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

FEATURE_SCHEMA_VERSION = "pit_v1"


@dataclass
class FeatureVector:
    values: dict[str, float]
    events: dict[str, datetime]
    schema_version: str = FEATURE_SCHEMA_VERSION

    @property
    def source_max_event_at(self) -> datetime | None:
        if not self.events:
            return None
        return max(self.events.values())

    def to_json(self) -> dict[str, Any]:
        return dict(self.values)


def _days_between(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / 86400.0


def build_demand_features(
    *,
    as_of: datetime,
    past_events: list[datetime],
    past_values: list[float] | None = None,
) -> FeatureVector:
    """Features for demand forecast from history strictly before as_of."""
    past = sorted(e for e in past_events if e <= as_of)
    values: dict[str, float] = {}
    events: dict[str, datetime] = {}

    def count_since(days: int) -> int:
        cutoff = as_of - timedelta(days=days)
        return sum(1 for e in past if e > cutoff)

    values["n_contracts_30d"] = float(count_since(30))
    values["n_contracts_90d"] = float(count_since(90))
    values["n_contracts_180d"] = float(count_since(180))
    values["n_contracts_365d"] = float(count_since(365))
    values["n_contracts_all"] = float(len(past))

    if past:
        last = past[-1]
        values["days_since_last"] = _days_between(as_of, last)
        events["days_since_last"] = last
        # cadence: mean inter-event days over last up to 10 events
        if len(past) >= 2:
            gaps = [_days_between(past[i], past[i - 1]) for i in range(1, len(past))]
            values["mean_cadence_days"] = sum(gaps) / len(gaps)
            events["mean_cadence_days"] = past[-1]
        else:
            values["mean_cadence_days"] = 365.0
        # same month last year activity
        year_ago_start = as_of - timedelta(days=365 + 15)
        year_ago_end = as_of - timedelta(days=365 - 15)
        values["same_window_ly"] = float(sum(1 for e in past if year_ago_start <= e <= year_ago_end))
        events["same_window_ly"] = past[-1]
    else:
        values["days_since_last"] = 9999.0
        values["mean_cadence_days"] = 9999.0
        values["same_window_ly"] = 0.0

    values["month_sin"] = float(__import__("math").sin(2 * 3.14159265 * as_of.month / 12))
    values["month_cos"] = float(__import__("math").cos(2 * 3.14159265 * as_of.month / 12))
    # month features are calendar knowledge available at as_of
    events["month_sin"] = as_of
    events["month_cos"] = as_of

    if past_values:
        paired = [(e, v) for e, v in zip(past_events, past_values) if e <= as_of and v is not None and v > 0]
        if paired:
            recent = [v for _, v in paired[-10:]]
            values["mean_value_recent"] = sum(recent) / len(recent)
            values["log_mean_value_recent"] = float(__import__("math").log1p(values["mean_value_recent"]))
            events["mean_value_recent"] = paired[-1][0]
            events["log_mean_value_recent"] = paired[-1][0]

    # Ensure every feature has an event_at
    for k in list(values.keys()):
        if k not in events:
            events[k] = as_of

    return FeatureVector(values=values, events=events)


def build_competitor_features(
    *,
    as_of: datetime,
    supplier_wins_at_ente: int,
    supplier_wins_in_category: int,
    supplier_wins_total: int,
    ente_contracts_total: int,
    category_contracts_total: int,
    days_since_supplier_win: float,
    value_band_wins: int,
    last_event_at: datetime | None,
) -> FeatureVector:
    values = {
        "supplier_wins_at_ente": float(supplier_wins_at_ente),
        "supplier_wins_in_category": float(supplier_wins_in_category),
        "supplier_wins_total": float(supplier_wins_total),
        "market_share_ente": (
            float(supplier_wins_at_ente) / float(ente_contracts_total) if ente_contracts_total > 0 else 0.0
        ),
        "market_share_category": (
            float(supplier_wins_in_category) / float(category_contracts_total) if category_contracts_total > 0 else 0.0
        ),
        "days_since_supplier_win": float(days_since_supplier_win),
        "value_band_wins": float(value_band_wins),
    }
    evt = last_event_at if last_event_at and last_event_at <= as_of else as_of
    events = {k: evt for k in values}
    return FeatureVector(values=values, events=events)


def build_discount_features(
    *,
    as_of: datetime,
    hist_discounts: list[tuple[datetime, float]],
    modality_code: float = 0.0,
    log_estimated_value: float = 0.0,
) -> FeatureVector:
    past = [(d, v) for d, v in hist_discounts if d <= as_of]
    values: dict[str, float] = {
        "modality_code": modality_code,
        "log_estimated_value": log_estimated_value,
        "n_hist_discounts": float(len(past)),
    }
    events: dict[str, datetime] = {
        "modality_code": as_of,
        "log_estimated_value": as_of,
        "n_hist_discounts": past[-1][0] if past else as_of,
    }
    if past:
        ds = sorted(v for _, v in past)
        mid = ds[len(ds) // 2]
        values["median_discount_hist"] = mid
        values["mean_discount_hist"] = sum(ds) / len(ds)
        values["p25_discount_hist"] = ds[max(0, len(ds) // 4)]
        values["p75_discount_hist"] = ds[min(len(ds) - 1, (3 * len(ds)) // 4)]
        for k in (
            "median_discount_hist",
            "mean_discount_hist",
            "p25_discount_hist",
            "p75_discount_hist",
        ):
            events[k] = past[-1][0]
    else:
        for k in (
            "median_discount_hist",
            "mean_discount_hist",
            "p25_discount_hist",
            "p75_discount_hist",
        ):
            values[k] = 0.0
            events[k] = as_of
    return FeatureVector(values=values, events=events)


def validate_feature_cutoff(fv: FeatureVector, as_of: datetime) -> list[str]:
    """Return list of feature names that leak past as_of."""
    return [k for k, edt in fv.events.items() if edt > as_of]
