"""Genuine predictive intelligence layer for extra-cli.

Claims are gated by the canonical registry. Heuristic scores are never
published as calibrated probabilities.
"""

from __future__ import annotations

__version__ = "0.1.0"

CLAIM_IDS = (
    "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
    "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
    "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
    "PREDICTIVE_MARKET_INTELLIGENCE_AVAILABLE",
    "EXTRA_WIN_PROBABILITY_AVAILABLE",
    "OPTIMAL_BID_RECOMMENDATION_AVAILABLE",
    "PREDICTIVE_INTELLIGENCE_FULLY_PROVEN",
)

CLAIM_STATES = (
    "NOT_IMPLEMENTED",
    "IMPLEMENTED",
    "DATA_BLOCKED",
    "BACKTEST_FAILED",
    "HISTORICAL_BACKTEST_PROVEN",
    "SHADOW_OPERATIONAL",
    "PROSPECTIVE_EVIDENCE_INSUFFICIENT",
    "PROSPECTIVE_CALIBRATED",
    "PRODUCTION_AVAILABLE",
    "SUSPENDED_DRIFT",
    "SUSPENDED_DATA_QUALITY",
)

TARGETS = (
    "demand_30d",
    "demand_60d",
    "demand_90d",
    "competitive_winner_p2a",
    "competitive_participation_p2b",
    "winning_discount_p3",
    "extra_win_probability_p4",
    "optimal_bid_p5",
)
