"""Pilot capacity metrics must stay independent of pilot sample."""

from __future__ import annotations

import pytest

from scripts.confenge_activation.operational_metrics import (
    PILOT_ACCEPTANCE_SAMPLE,
    assert_not_pilot_as_capacity,
    build_capacity_metrics,
    business_hours_from_window,
    min_operational_reserve,
)


def test_pilot_sample_is_50_quality_only() -> None:
    assert PILOT_ACCEPTANCE_SAMPLE == 50


def test_min_operational_reserve_warmbly_defaults() -> None:
    # 10/h × 9h (09:00-18:00) × 10 business days = 900
    assert min_operational_reserve(emails_per_hour=10, business_hours_per_day=9) == 900


def test_business_hours_from_window() -> None:
    assert business_hours_from_window("09:00", "18:00") == 9.0
    assert business_hours_from_window("08:30", "17:30") == 9.0


def test_capacity_metrics_independent() -> None:
    m = build_capacity_metrics(
        email_send_ready_distinct_companies=60,
        active_hot_set_size=10,
        emails_per_hour=10,
        business_hours_per_day=9,
    )
    assert m["PILOT_ACCEPTANCE_SAMPLE"] == 50
    assert m["NATIONAL_EMAIL_SEND_READY_RESERVOIR"] == 60
    assert m["ACTIVE_HOT_SET"] == 10
    assert m["MIN_OPERATIONAL_RESERVE"] == 900
    assert m["reserve_gate_ok"] is False
    assert m["pilot_is_not_capacity"] is True


def test_reserve_gate_passes_at_threshold() -> None:
    m = build_capacity_metrics(
        email_send_ready_distinct_companies=900,
        active_hot_set_size=20,
        emails_per_hour=10,
        business_hours_per_day=9,
    )
    assert m["reserve_gate_ok"] is True


def test_refuse_pilot_as_capacity() -> None:
    with pytest.raises(ValueError, match="quality-only"):
        assert_not_pilot_as_capacity(50, context="enrichment")
    assert_not_pilot_as_capacity(None)
    assert_not_pilot_as_capacity(200)
