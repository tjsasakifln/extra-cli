"""Supply-driven hot-set expansion for EMAIL_SEND_READY stock.

Does not relax quality gates. Expands the processed batch until
ready_count >= target or the eligible reservoir for the cycle is exhausted.

Yield is observed from the current cycle (never a hardcoded 15%/30%).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SupplyExpansionPlan:
    ready_supply_target: int
    ready_count: int
    processed_count: int
    observed_yield: float
    next_batch_size: int
    should_expand: bool
    stop_reason: str

    def as_dict(self) -> dict:
        return {
            "ready_supply_target": self.ready_supply_target,
            "ready_count": self.ready_count,
            "processed_count": self.processed_count,
            "observed_yield": self.observed_yield,
            "next_batch_size": self.next_batch_size,
            "should_expand": self.should_expand,
            "stop_reason": self.stop_reason,
        }


def plan_supply_expansion(
    *,
    ready_count: int,
    processed_count: int,
    ready_supply_target: int,
    remaining_eligible: int,
    max_hot_set: int,
    min_batch: int = 20,
) -> SupplyExpansionPlan:
    """Decide whether to expand the next expensive enrichment batch.

    next_batch_size uses observed yield when processed_count > 0:
      need = target - ready
      next = ceil(need / yield) clamped to [min_batch, remaining, max_hot_set - processed]
    When no yield yet, take min_batch (or remaining).
    """
    target = max(1, int(ready_supply_target))
    ready = max(0, int(ready_count))
    processed = max(0, int(processed_count))
    remaining = max(0, int(remaining_eligible))
    cap = max(1, int(max_hot_set))

    if ready >= target:
        return SupplyExpansionPlan(
            ready_supply_target=target,
            ready_count=ready,
            processed_count=processed,
            observed_yield=(ready / processed) if processed else 0.0,
            next_batch_size=0,
            should_expand=False,
            stop_reason="supply_met",
        )
    if remaining <= 0:
        return SupplyExpansionPlan(
            ready_supply_target=target,
            ready_count=ready,
            processed_count=processed,
            observed_yield=(ready / processed) if processed else 0.0,
            next_batch_size=0,
            should_expand=False,
            stop_reason="reservoir_exhausted",
        )
    if processed >= cap:
        return SupplyExpansionPlan(
            ready_supply_target=target,
            ready_count=ready,
            processed_count=processed,
            observed_yield=(ready / processed) if processed else 0.0,
            next_batch_size=0,
            should_expand=False,
            stop_reason="max_hot_set_reached",
        )

    need = target - ready
    yld = (ready / processed) if processed > 0 else 0.0
    if yld > 0:
        # ceil(need / yld)
        raw = int((need + yld - 1e-12) // yld) if yld else need
        # more portable ceil:
        import math

        raw = int(math.ceil(need / yld))
    else:
        raw = max(min_batch, need)  # unknown yield: expand by at least min_batch

    room = max(0, cap - processed)
    next_n = max(min_batch, raw)
    next_n = min(next_n, remaining, room)
    if next_n <= 0:
        return SupplyExpansionPlan(
            ready_supply_target=target,
            ready_count=ready,
            processed_count=processed,
            observed_yield=yld,
            next_batch_size=0,
            should_expand=False,
            stop_reason="no_room",
        )
    return SupplyExpansionPlan(
        ready_supply_target=target,
        ready_count=ready,
        processed_count=processed,
        observed_yield=yld,
        next_batch_size=next_n,
        should_expand=True,
        stop_reason="expand",
    )
