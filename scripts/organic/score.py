"""Content Value Score — commercial impact, not keyword volume.

Default weights (sum 100) match the organic inbound objective:

  commercial_intent          25
  service_fit                20
  data_moat                  20
  demand_evidence            15
  topical_authority          10
  freshness_trigger           5
  competitive_opportunity     5

Score is advisory for ranking. Mandatory indexability gates still block publish.
"""

from __future__ import annotations

from typing import Any

CONTENT_VALUE_WEIGHTS: dict[str, int] = {
    "commercial_intent": 25,
    "service_fit": 20,
    "data_moat": 20,
    "demand_evidence": 15,
    "topical_authority": 10,
    "freshness_trigger": 5,
    "competitive_opportunity": 5,
}

# Penalty magnitudes subtracted after weighted sum (clamped 0–100)
PENALTY_MAGNITUDES: dict[str, int] = {
    "commodity_content": 15,
    "serp_incompatible": 12,
    "missing_evidence": 18,
    "low_confidence": 10,
    "cannibalization": 14,
    "thin_content": 20,
    "low_differentiation": 12,
    "off_positioning": 25,
    "legal_risk": 30,
    "purely_speculative": 22,
}

INTENT_COMMERCIAL = {
    "bofu": 1.0,
    "mofu": 0.72,
    "tofu": 0.38,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _clamp100(x: float) -> int:
    return int(max(0, min(100, round(x))))


def compute_content_value_score(
    *,
    intent_stage: str = "mofu",
    service_fit: float = 0.0,
    data_moat: float = 0.0,
    demand_evidence: float = 0.0,
    topical_authority: float = 0.5,
    freshness_trigger: float = 0.3,
    competitive_opportunity: float = 0.4,
    penalties: list[str] | None = None,
    weights: dict[str, int] | None = None,
    penalty_magnitudes: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Return 0–100 score + breakdown. Parametrizable weights and penalties.

    All component inputs are expected on 0–1 (higher is better), except
    penalties which are string codes from PENALTY_MAGNITUDES.
    """
    w = dict(weights or CONTENT_VALUE_WEIGHTS)
    # Normalize if custom weights don't sum to 100
    wsum = sum(w.values()) or 1
    scale = 100.0 / wsum

    intent_key = (intent_stage or "mofu").strip().lower()
    commercial = INTENT_COMMERCIAL.get(intent_key, 0.5)

    comps = {
        "commercial_intent": _clamp01(commercial),
        "service_fit": _clamp01(service_fit),
        "data_moat": _clamp01(data_moat),
        "demand_evidence": _clamp01(demand_evidence),
        "topical_authority": _clamp01(topical_authority),
        "freshness_trigger": _clamp01(freshness_trigger),
        "competitive_opportunity": _clamp01(competitive_opportunity),
    }

    # Weighted contribution = component_0_1 * weight * (100/sum_weights)
    breakdown = {
        k: int(round(_clamp01(comps[k]) * w.get(k, 0) * scale))
        for k in w
        if k in comps
    }
    raw_total = sum(breakdown.values())

    pens = list(penalties or [])
    mag = dict(penalty_magnitudes or PENALTY_MAGNITUDES)
    penalty_applied: dict[str, int] = {}
    penalty_sum = 0
    for p in pens:
        amount = int(mag.get(p, 0))
        if amount > 0:
            penalty_applied[p] = amount
            penalty_sum += amount

    total = _clamp100(raw_total - penalty_sum)

    return {
        "score": total,
        "raw_score": _clamp100(raw_total),
        "breakdown": breakdown,
        "weights": {k: int(round(v * scale)) for k, v in w.items()},
        "penalties": penalty_applied,
        "penalty_total": penalty_sum,
        "components_0_1": comps,
        "note": (
            "Content Value Score ranks opportunities by expected commercial "
            "impact; it never overrides mandatory indexability gates."
        ),
    }


def score_opportunity_dict(opp: dict[str, Any], weights: dict[str, int] | None = None) -> dict[str, Any]:
    """Score from a partially filled opportunity dict."""
    return compute_content_value_score(
        intent_stage=str(opp.get("intent") or opp.get("intent_stage") or "mofu"),
        service_fit=float(opp.get("service_fit_score") or opp.get("commercial_fit") or 0),
        data_moat=float(opp.get("data_moat_score") or (1.0 if opp.get("unique_data_available") else 0.2)),
        demand_evidence=float(opp.get("demand_strength") or 0),
        topical_authority=float(opp.get("topical_authority_score") or 0.5),
        freshness_trigger=float(opp.get("freshness_score") or 0.3),
        competitive_opportunity=float(opp.get("competitive_score") or 0.4),
        penalties=list(opp.get("penalties") or []),
        weights=weights,
    )
