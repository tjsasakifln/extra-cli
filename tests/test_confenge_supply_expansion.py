"""Supply-driven expansion: quality never relaxed; yield observed not hardcoded."""

from __future__ import annotations

from scripts.confenge_activation.policy import load_policy
from scripts.confenge_activation.supply import plan_supply_expansion
from scripts.confenge_contact_resolution.send_readiness import ready_supply_target


def test_ready_supply_target_default_360() -> None:
    assert ready_supply_target(max_send_rate=20, send_window_hours=9, ready_supply_target_days=2) == 360
    pol = load_policy()
    assert pol.capacity.ready_supply_target() == 360


def test_expansion_stops_when_supply_met() -> None:
    p = plan_supply_expansion(
        ready_count=360,
        processed_count=2000,
        ready_supply_target=360,
        remaining_eligible=1000,
        max_hot_set=4000,
    )
    assert p.should_expand is False
    assert p.stop_reason == "supply_met"


def test_expansion_uses_observed_yield_not_hardcoded() -> None:
    # 10 ready out of 100 processed => 10% yield; need 50 more => ~500 next
    p = plan_supply_expansion(
        ready_count=10,
        processed_count=100,
        ready_supply_target=60,
        remaining_eligible=5000,
        max_hot_set=4000,
        min_batch=20,
    )
    assert p.should_expand is True
    assert abs(p.observed_yield - 0.1) < 1e-9
    assert p.next_batch_size == 500  # ceil(50 / 0.1)


def test_expansion_never_relaxes_when_reservoir_empty() -> None:
    p = plan_supply_expansion(
        ready_count=5,
        processed_count=100,
        ready_supply_target=360,
        remaining_eligible=0,
        max_hot_set=4000,
    )
    assert p.should_expand is False
    assert p.stop_reason == "reservoir_exhausted"


def test_production_planned_capacity_not_limit_downstream_200() -> None:
    pol = load_policy()
    planned = pol.capacity.planned_capacity()
    assert planned != 200
    assert planned >= pol.capacity.min_hot_set
