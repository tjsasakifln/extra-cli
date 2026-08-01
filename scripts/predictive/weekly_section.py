"""Claim-gated predictive section for weekly pack (no invented PRODUCTION claims)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scripts.predictive.claims import load_registry
from scripts.predictive.profile_calibration import personalization_blockers


def build_weekly_predictive_section() -> dict[str, Any]:
    """Build honest predictive payload for weekly cycle consumers."""
    reg = load_registry()
    public = reg.to_public_dict()
    claims = public["claims"]

    def snap(claim_id: str) -> dict[str, Any]:
        c = claims[claim_id]
        return {
            "claim_id": claim_id,
            "state": c["state"],
            "external_availability_allowed": c.get("external_availability_allowed", False),
            "blockers": c.get("blockers") or [],
            "limitations": c.get("limitations") or [],
            "model_id": c.get("model_id"),
            "model_version": c.get("model_version"),
            "prediction_allowed": c["state"] == "PRODUCTION_AVAILABLE",
        }

    demand = snap("PREDICTIVE_DEMAND_FORECAST_AVAILABLE")
    competitive = snap("PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE")
    discount = snap("PREDICTIVE_WINNING_DISCOUNT_AVAILABLE")
    extra_win = snap("EXTRA_WIN_PROBABILITY_AVAILABLE")
    optimal = snap("OPTIMAL_BID_RECOMMENDATION_AVAILABLE")
    fully = snap("PREDICTIVE_INTELLIGENCE_FULLY_PROVEN")

    # Only include win-probability block when production-allowed
    win_block: dict[str, Any] = {
        "included": extra_win["prediction_allowed"],
        "claim": extra_win,
        "nomenclature_if_market_only": "CALIBRATED_MARKET_WIN_LIKELIHOOD",
        "note": (
            "Probabilidade de vitória da Extra omitida — claim não PRODUCTION_AVAILABLE"
            if not extra_win["prediction_allowed"]
            else "Permitido apenas com modelo calibrado aprovado"
        ),
    }

    profile = personalization_blockers()

    return {
        "section": "predictive_intelligence",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "commercial_recommendation": public["commercial_recommendation"],
        "vocabulary": {
            "allowed_when_production": "probabilidade calibrada",
            "otherwise": "score não calibrado / cenário heurístico / dados insuficientes",
        },
        "claims": {
            "demand": demand,
            "competitive_p2a": competitive,
            "competitive_p2b": {
                "state": "DATA_BLOCKED",
                "note": "Participação exige listas reais de participantes; não inferir de não-vitória",
            },
            "winning_discount": discount,
            "extra_win": extra_win,
            "optimal_bid": optimal,
            "fully_proven": fully,
        },
        "demand_forecasts": {
            "available": demand["prediction_allowed"],
            "state": demand["state"],
            "items": [],
            "reason_if_empty": (
                None
                if demand["prediction_allowed"]
                else f"Demanda claim={demand['state']} — sem publicação de probabilidade"
            ),
        },
        "competitors_probable": {
            "available": competitive["state"]
            in {
                "PRODUCTION_AVAILABLE",
                "PROSPECTIVE_CALIBRATED",
                "SHADOW_OPERATIONAL",
                "HISTORICAL_BACKTEST_PROVEN",
            },
            "state": competitive["state"],
            "mode": "shadow_or_historical_only"
            if competitive["state"] != "PRODUCTION_AVAILABLE"
            else "production",
            "items": [],
            "limitations": competitive["limitations"] + competitive["blockers"],
            "p2b_participation_available": False,
        },
        "discount_band": {
            "available": discount["prediction_allowed"],
            "state": discount["state"],
            "p10": None,
            "p50": None,
            "p90": None,
            "reason_if_empty": (
                None
                if discount["prediction_allowed"]
                else f"Desconto claim={discount['state']}"
            ),
        },
        "win_probability": win_block,
        "drift": {
            "status": "see_monitor",
            "note": "python -m scripts.predictive monitor",
        },
        "backtest": {
            "note": "See artifacts/campaigns/EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01/backtest-summary.json",
        },
        "shadow_status": {
            "competitive": competitive["state"],
            "prospective_soak_complete": False,
        },
        "blockers": {
            "human_profile": profile.get("missing_critical") or [],
            "calendar": [
                "Prospective soak ≥30d / ≥100 mature outcomes not elapsed",
            ],
            "source": [
                b
                for c in (demand, competitive, discount, extra_win)
                for b in (c.get("blockers") or [])
            ],
        },
        "disclaimer": (
            "Nenhuma capacidade preditiva está PRODUCTION_AVAILABLE neste pacote "
            "salvo se claim_state indicar explicitamente. Scores heurísticos do "
            "bid_simulator NÃO são probabilidade de vitória."
        ),
    }
