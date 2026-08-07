"""Freshness decay for contact observations."""

from __future__ import annotations

from datetime import date, datetime


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # ISO date or datetime
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def freshness_score(
    source_date: str | None,
    *,
    as_of: date | None = None,
    half_life_days: int = 365,
) -> tuple[float, int | None]:
    """Return (freshness in [0,1], age_days).

    Missing date → mild penalty (0.7) rather than inventing recency.
    Older than ~3 half-lives approaches floor 0.1.
    """
    today = as_of or date.today()
    d = _parse_date(source_date)
    if d is None:
        return 0.7, None
    age = (today - d).days
    if age < 0:
        age = 0
    if half_life_days <= 0:
        return 1.0, age
    # exponential decay: 0.5 ** (age / half_life)

    score = 0.5 ** (age / float(half_life_days))
    score = max(0.1, min(1.0, score))
    return round(score, 4), age
