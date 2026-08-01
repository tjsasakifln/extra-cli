"""Deterministic per-entity multi-source process budget allocation.

``max_processes`` is a **total** ceiling per entity for one collection cycle.
Budgets granted to sources MUST satisfy::

    sum(source_budget) <= entity_max_processes

Sources that receive 0 are marked ``NOT_QUERIED_BUDGET`` (never as zero docs).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# Default relative weights when caller does not pass per-source caps.
# Higher weight → more share of the global budget (deterministic order tie-break).
DEFAULT_SOURCE_WEIGHTS: dict[str, int] = {
    "pncp": 3,
    "sc_compras": 2,
    "ciga_ckan": 2,
    "ciga_dom": 1,
    "generic_html": 1,
}


def allocate_source_budgets(
    sources: Sequence[str],
    *,
    max_processes: int,
    per_source_caps: Mapping[str, int] | None = None,
    weights: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Allocate integer process budgets across sources under a global ceiling.

    Algorithm (deterministic):
    1. Preserve caller order of ``sources``.
    2. Base share proportional to weight (default from DEFAULT_SOURCE_WEIGHTS).
    3. Floor each share; distribute remainder one-by-one in source order.
    4. Apply optional per-source caps without exceeding residual global budget.
    5. Guarantee ``sum(budgets) <= max_processes``.
    6. Sources with budget 0 are listed under ``not_queried_budget``.
    """
    srcs = [str(s) for s in sources if str(s)]
    ceiling = max(0, int(max_processes))
    caps = {str(k): max(0, int(v)) for k, v in (per_source_caps or {}).items()}
    wmap = dict(DEFAULT_SOURCE_WEIGHTS)
    if weights:
        wmap.update({str(k): max(0, int(v)) for k, v in weights.items()})

    if not srcs or ceiling <= 0:
        return {
            "max_processes": ceiling,
            "budgets": {s: 0 for s in srcs},
            "not_queried_budget": list(srcs),
            "queried": [],
            "sum_budgets": 0,
            "allocation_method": "entity_global_ceiling_v1",
        }

    weights_list = [max(1, wmap.get(s, 1)) for s in srcs]
    total_w = sum(weights_list) or len(srcs)
    # Initial proportional floor
    raw = [ceiling * w / total_w for w in weights_list]
    budgets = [int(x) for x in raw]
    # Distribute remainder to earliest sources (stable)
    rem = ceiling - sum(budgets)
    i = 0
    while rem > 0 and srcs:
        budgets[i % len(srcs)] += 1
        rem -= 1
        i += 1

    # Apply per-source caps; reclaim excess for later sources that can take more
    for idx, s in enumerate(srcs):
        if s in caps:
            budgets[idx] = min(budgets[idx], caps[s])

    # Reclaim if sum still exceeds ceiling (should not, but fail-closed)
    while sum(budgets) > ceiling:
        # reduce from the end
        for idx in range(len(budgets) - 1, -1, -1):
            if budgets[idx] > 0 and sum(budgets) > ceiling:
                budgets[idx] -= 1

    # If caps left unused budget, try to give to uncapped sources with capacity
    used = sum(budgets)
    leftover = ceiling - used
    if leftover > 0:
        for idx, s in enumerate(srcs):
            if leftover <= 0:
                break
            cap = caps.get(s)
            if cap is None:
                budgets[idx] += leftover
                leftover = 0
            else:
                room = max(0, cap - budgets[idx])
                take = min(room, leftover)
                budgets[idx] += take
                leftover -= take

    budget_map = {s: int(b) for s, b in zip(srcs, budgets, strict=True)}
    # Final hard clamp
    running = 0
    for s in srcs:
        allowed = max(0, ceiling - running)
        budget_map[s] = min(budget_map[s], allowed)
        running += budget_map[s]

    not_queried = [s for s in srcs if budget_map[s] <= 0]
    queried = [s for s in srcs if budget_map[s] > 0]
    total = sum(budget_map.values())
    if total > ceiling:
        raise RuntimeError(
            f"budget overflow: sum={total} > max_processes={ceiling} budgets={budget_map}"
        )

    return {
        "max_processes": ceiling,
        "budgets": budget_map,
        "not_queried_budget": not_queried,
        "queried": queried,
        "sum_budgets": total,
        "weights": {s: max(1, wmap.get(s, 1)) for s in srcs},
        "per_source_caps": caps,
        "allocation_method": "entity_global_ceiling_v1",
    }
