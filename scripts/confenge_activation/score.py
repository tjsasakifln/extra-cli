"""Deterministic activation_score (0–100) — ordering only, never probability."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from scripts.confenge_activation.models import FiredTrigger, ScoreComponents
from scripts.confenge_activation.policy import ActivationPolicy


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def freshness_score(as_of: date, event_date: date | None, policy: ActivationPolicy) -> float:
    if event_date is None:
        return 10.0
    days = max(0, (as_of - event_date).days)
    for band in policy.freshness_bands:
        if days <= int(band.get("max_days", 99999)):
            return float(band.get("score", 10))
    return 10.0


def evidence_quality_score(row: dict[str, Any], policy: ActivationPolicy) -> float:
    eq = policy.evidence_quality
    ce = row.get("construction_evidence") if isinstance(row.get("construction_evidence"), dict) else {}
    fit = str(ce.get("sector_fit") or ce.get("fit") or "").upper()
    if fit == "CONFIRMED_ENGINEERING":
        base = float(eq.get("confirmed_engineering", 90))
    elif fit == "STRONG_ENGINEERING_FIT":
        base = float(eq.get("strong_engineering_fit", 70))
    elif fit == "POSSIBLE_ENGINEERING_FIT":
        base = float(eq.get("possible_engineering_fit", 45))
    else:
        base = float(eq.get("default", 25))
    port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    recent = port.get("recent_contracts") or []
    if isinstance(recent, list) and len(recent) > 0:
        base = _clamp(base + float(eq.get("with_recent_contracts_sample", 15)))
    return _clamp(base)


def commercial_relevance_score(row: dict[str, Any], policy: ActivationPolicy) -> float:
    """Portfolio breadth + damped value + fit. Mega-contract cannot dominate."""
    mat = policy.materiality
    port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    ce = row.get("construction_evidence") if isinstance(row.get("construction_evidence"), dict) else {}

    active = float(port.get("active_contract_count") or 0)
    orgaos = port.get("orgaos") or []
    n_org = float(len(orgaos)) if isinstance(orgaos, list) else float(orgaos or 0)
    ufs = port.get("ufs_atuacao") or []
    n_uf = float(len(ufs)) if isinstance(ufs, list) else float(ufs or 0)
    breadth = _clamp((active * 2.0 + n_org * 1.5 + n_uf * 2.0), 0, 100)

    value = float(port.get("value_recent_brl") or port.get("value_total_brl") or 0)
    log_cap = float(mat.get("value_log_cap", 12.0))
    if value > 0:
        # Same damping spirit as universe priority: log10(1+v/1e5)
        value_pts = min(log_cap, math.log10(1.0 + value / 1e5) * 2.0) / log_cap * 100.0
    else:
        value_pts = 0.0

    fit = str(ce.get("sector_fit") or "").upper()
    if fit == "CONFIRMED_ENGINEERING":
        fit_pts = 100.0
    elif fit == "STRONG_ENGINEERING_FIT":
        fit_pts = 80.0
    elif fit == "POSSIBLE_ENGINEERING_FIT":
        fit_pts = 50.0
    else:
        fit_pts = 20.0

    w_val = float(mat.get("value_weight_in_relevance", 0.35))
    w_br = float(mat.get("portfolio_breadth_weight", 0.40))
    w_fit = float(mat.get("construction_fit_weight", 0.25))
    # Normalize weights
    wsum = w_val + w_br + w_fit
    if wsum <= 0:
        w_val, w_br, w_fit = 0.35, 0.40, 0.25
        wsum = 1.0
    w_val, w_br, w_fit = w_val / wsum, w_br / wsum, w_fit / wsum
    return _clamp(value_pts * w_val + breadth * w_br + fit_pts * w_fit)


def trigger_strength_score(fired: list[FiredTrigger]) -> float:
    if not fired:
        return 0.0
    # Best trigger + diminishing secondary
    best = max(f.strength for f in fired)
    secondary = sum(f.strength for f in fired) - best
    return _clamp(best + 0.15 * secondary)


def compute_activation_score(
    row: dict[str, Any],
    fired: list[FiredTrigger],
    *,
    policy: ActivationPolicy,
    as_of: date,
) -> tuple[float, ScoreComponents]:
    """Weighted 0–100 ordering score. Deterministic for same inputs+policy."""
    w = policy.score_weights
    # Raw components on 0–100 scale before weighting
    ts_raw = trigger_strength_score(fired)
    event = None
    if fired:
        event = _parse_date(fired[0].event_date)
    fr_raw = freshness_score(as_of, event, policy)
    eq_raw = evidence_quality_score(row, policy)
    cr_raw = commercial_relevance_score(row, policy)

    # Apply weights (weights sum to 100 → score already 0–100)
    components = ScoreComponents(
        trigger_strength=ts_raw * (w.trigger_strength / 100.0),
        freshness=fr_raw * (w.freshness / 100.0),
        evidence_quality=eq_raw * (w.evidence_quality / 100.0),
        commercial_relevance=cr_raw * (w.commercial_relevance / 100.0),
    )
    total = _clamp(components.total())
    return round(total, 4), components
