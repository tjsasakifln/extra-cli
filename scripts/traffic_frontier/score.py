"""Traffic-frontier score — demand × pain × coverage × edge.

Campaign weights (sum 100), distinct from organic Content Value Score:

  search_question_demand       20
  commercial_pain_ticket       20
  data_coverage_freshness      20
  proprietary_differentiation  15
  citability                   10
  time_to_publish              10
  maintenance_cost              5  (inverted)

Score ranks. Hard gates in gates.py decide READY / HOLD / REJECT.
Absence of GSC does not zero demand when a MARKET_JOB is present.
External keyword volumes are never invented here.
"""

from __future__ import annotations

from typing import Any

FRONTIER_WEIGHTS: dict[str, int] = {
    "search_question_demand": 20,
    "commercial_pain_ticket": 20,
    "data_coverage_freshness": 20,
    "proprietary_differentiation": 15,
    "citability": 10,
    "time_to_publish": 10,
    "maintenance_cost": 5,
}

# Subtracted after the weighted sum; disconnected CTA cannot pass gates alone.
PENALTY_MAGNITUDES: dict[str, int] = {
    "disconnected_cta": 12,
    "weak_offer_bridge": 8,
    "thin_citability": 6,
}

MARKET_JOB_DEMAND_FLOOR = 0.35
GSC_ABSENT_NOTE = (
    "SEARCH_SIGNAL ausente (sem GSC). Demanda inferida do MARKET_JOB; volume de ferramenta externa não foi inventado."
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp100(value: float) -> int:
    return int(max(0, min(100, round(value))))


def demand_from_signals(
    *,
    gsc_impressions: float = 0.0,
    gsc_clicks: float = 0.0,
    gsc_position: float = 0.0,
    market_job_present: bool = False,
    market_job_plausibility: float = 0.0,
) -> dict[str, Any]:
    """Map GSC and/or MARKET_JOB to a 0–1 demand component.

    Missing GSC never forces 0 when a concrete MARKET_JOB exists.
    """
    impressions = max(0.0, float(gsc_impressions or 0.0))
    clicks = max(0.0, float(gsc_clicks or 0.0))
    position = max(0.0, float(gsc_position or 0.0))
    has_gsc = impressions > 0.0 or clicks > 0.0
    plausibility = _clamp01(market_job_plausibility)

    gsc_component = 0.0
    if has_gsc:
        pos_score = 0.0
        if 4 <= position <= 15:
            pos_score = 0.55
        elif 1 <= position < 4:
            pos_score = 0.7
        elif position > 15:
            pos_score = 0.25
        imp_score = min(1.0, impressions / 50.0) * 0.35
        click_score = min(1.0, clicks / 5.0) * 0.35
        gsc_component = _clamp01(pos_score + imp_score + click_score)

    job_component = 0.0
    if market_job_present:
        job_component = _clamp01(MARKET_JOB_DEMAND_FLOOR + 0.5 * plausibility)

    if has_gsc and market_job_present:
        demand = _clamp01(0.55 * gsc_component + 0.45 * job_component)
        source = "gsc+market_job"
    elif has_gsc:
        demand = gsc_component
        source = "gsc"
    elif market_job_present:
        demand = job_component
        source = "inferred_market_job"
    else:
        demand = 0.0
        source = "none"

    return {
        "demand_0_1": demand,
        "source": source,
        "gsc_present": has_gsc,
        "market_job_present": bool(market_job_present),
        "note": None if has_gsc else (GSC_ABSENT_NOTE if market_job_present else None),
    }


def compute_frontier_score(
    *,
    search_question_demand: float = 0.0,
    commercial_pain_ticket: float = 0.0,
    data_coverage_freshness: float = 0.0,
    proprietary_differentiation: float = 0.0,
    citability: float = 0.0,
    time_to_publish: float = 0.0,
    maintenance_cost: float = 0.5,
    penalties: list[str] | None = None,
    weights: dict[str, int] | None = None,
    penalty_magnitudes: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Return 0–100 score + breakdown. Maintenance is inverted (high cost hurts).

    Component inputs are 0–1 (higher is better) except ``maintenance_cost``,
    where 1.0 means expensive to keep current.
    """
    weight_map = dict(weights or FRONTIER_WEIGHTS)
    weight_sum = sum(weight_map.values()) or 1
    if weight_sum != 100:
        raise ValueError(f"frontier weights must sum 100, got {weight_sum}")

    components = {
        "search_question_demand": _clamp01(search_question_demand),
        "commercial_pain_ticket": _clamp01(commercial_pain_ticket),
        "data_coverage_freshness": _clamp01(data_coverage_freshness),
        "proprietary_differentiation": _clamp01(proprietary_differentiation),
        "citability": _clamp01(citability),
        "time_to_publish": _clamp01(time_to_publish),
        "maintenance_cost": _clamp01(1.0 - float(maintenance_cost)),
    }

    breakdown = {key: int(round(components[key] * weight_map[key])) for key in weight_map if key in components}
    raw_total = sum(breakdown.values())

    penalty_applied: dict[str, int] = {}
    penalty_sum = 0
    magnitudes = dict(penalty_magnitudes or PENALTY_MAGNITUDES)
    for code in penalties or []:
        amount = int(magnitudes.get(code, 0))
        if amount > 0:
            penalty_applied[code] = amount
            penalty_sum += amount

    return {
        "score": _clamp100(raw_total - penalty_sum),
        "raw_score": _clamp100(raw_total),
        "breakdown": breakdown,
        "weights": dict(weight_map),
        "penalties": penalty_applied,
        "penalty_total": penalty_sum,
        "components_0_1": components,
        "maintenance_inverted": True,
        "note": (
            "Traffic frontier score ranks factual publish candidates; "
            "it never overrides hard gates and never authorizes index/publish."
        ),
    }
