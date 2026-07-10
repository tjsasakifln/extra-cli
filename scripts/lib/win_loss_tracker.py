#!/usr/bin/env python3
"""
Win/Loss Tracker — Registra resultados de licitações para calibrar modelos.

Persiste outcomes em JSON local (data/win_loss_tracker.json) para que
o bid_score threshold e victory_profile sejam recalibrados ao longo do tempo.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACKER_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "win_loss_tracker.json"


def _load() -> dict:
    """Load tracker data from disk."""
    if not TRACKER_FILE.exists():
        return {"outcomes": [], "_version": "1.0.0"}
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"outcomes": [], "_version": "1.0.0"}


def _save(data: dict) -> None:
    """Save tracker data to disk."""
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def record_outcome(
    cnpj: str,
    edital_id: str,
    outcome: str,
    valor_proposta: float = 0,
    valor_vencedor: float = 0,
    bid_score: float = 0,
    victory_fit: float = 0,
    notes: str = "",
) -> dict:
    """Record a bid outcome for future calibration.

    Args:
        cnpj: Company CNPJ (14 digits).
        edital_id: Edital identifier (e.g., PNCP number).
        outcome: One of 'win', 'loss', 'no_bid', 'deserted', 'cancelled'.
        valor_proposta: Value of the company's bid (R$).
        valor_vencedor: Value of the winning bid (R$).
        bid_score: Bid/No-Bid composite score at time of analysis (0-1).
        victory_fit: Victory profile fit score at time of analysis (0-1).
        notes: Optional free-text notes.

    Returns:
        The recorded entry dict.
    """
    valid_outcomes = {"win", "loss", "no_bid", "deserted", "cancelled"}
    if outcome not in valid_outcomes:
        raise ValueError(f"outcome must be one of {valid_outcomes}, got '{outcome}'")

    data = _load()
    entry = {
        "cnpj": cnpj,
        "edital_id": edital_id,
        "outcome": outcome,
        "valor_proposta": valor_proposta,
        "valor_vencedor": valor_vencedor,
        "bid_score_at_time": bid_score,
        "victory_fit_at_time": victory_fit,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data["outcomes"].append(entry)
    _save(data)
    return entry


def calibration_report(cnpj: str | None = None) -> dict[str, Any]:
    """Generate calibration metrics for a given CNPJ (or all CNPJs).

    Compares bid_score distribution for wins vs losses to suggest
    threshold adjustments.

    Returns:
        Dict with calibration metrics and suggested threshold.
    """
    data = _load()
    outcomes = data.get("outcomes", [])

    if cnpj:
        outcomes = [o for o in outcomes if o["cnpj"] == cnpj]

    if not outcomes:
        return {"status": "no_data", "total": 0}

    wins = [o for o in outcomes if o["outcome"] == "win"]
    losses = [o for o in outcomes if o["outcome"] == "loss"]
    no_bids = [o for o in outcomes if o["outcome"] == "no_bid"]

    win_scores = [o["bid_score_at_time"] for o in wins if o.get("bid_score_at_time")]
    loss_scores = [o["bid_score_at_time"] for o in losses if o.get("bid_score_at_time")]

    avg_win = statistics.mean(win_scores) if win_scores else 0
    avg_loss = statistics.mean(loss_scores) if loss_scores else 0

    # Suggest threshold: midpoint between avg win and avg loss scores
    suggested_threshold = 0.45  # Default
    if win_scores and loss_scores:
        suggested_threshold = round((avg_win + avg_loss) / 2, 3)
    elif win_scores:
        suggested_threshold = round(min(win_scores) * 0.9, 3)

    # Value recovery rate
    total_proposed = sum(o.get("valor_proposta", 0) for o in wins)
    total_won = sum(o.get("valor_vencedor", 0) for o in wins)

    return {
        "status": "ok",
        "total": len(outcomes),
        "wins": len(wins),
        "losses": len(losses),
        "no_bids": len(no_bids),
        "win_rate": round(len(wins) / max(1, len(wins) + len(losses)), 3),
        "avg_bid_score_wins": round(avg_win, 3),
        "avg_bid_score_losses": round(avg_loss, 3),
        "suggested_threshold": suggested_threshold,
        "total_value_proposed": total_proposed,
        "total_value_won": total_won,
        "cnpj_filter": cnpj,
    }


def list_outcomes(cnpj: str | None = None, limit: int = 20) -> list[dict]:
    """List recent outcomes, optionally filtered by CNPJ."""
    data = _load()
    outcomes = data.get("outcomes", [])
    if cnpj:
        outcomes = [o for o in outcomes if o["cnpj"] == cnpj]
    return outcomes[-limit:]
