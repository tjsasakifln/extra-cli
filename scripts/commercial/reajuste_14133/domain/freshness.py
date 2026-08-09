"""Source freshness score from real dates (no fixed 0.55)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def compute_source_freshness(
    *,
    as_of: date,
    data_publicacao: Any = None,
    data_assinatura: Any = None,
    data_atualizacao_fonte: Any = None,
    last_seen_at: Any = None,
    source_event_date: Any = None,
) -> float:
    """Return freshness in [0, 1] from most recent known source date.

    Recent updates → higher score. Unknown dates → low but non-zero (0.2).
    """
    candidates = [
        _parse_date(data_atualizacao_fonte),
        _parse_date(last_seen_at),
        _parse_date(source_event_date),
        _parse_date(data_publicacao),
        _parse_date(data_assinatura),
    ]
    known = [d for d in candidates if d is not None]
    if not known:
        return 0.20
    latest = max(known)
    age_days = (as_of - latest).days
    if age_days < 0:
        age_days = 0
    # 0 days → 1.0; 365 days → ~0.55; 3 years → ~0.25; 5y+ → ~0.15
    if age_days <= 30:
        return 0.95
    if age_days <= 90:
        return 0.85
    if age_days <= 180:
        return 0.75
    if age_days <= 365:
        return 0.60
    if age_days <= 730:
        return 0.45
    if age_days <= 1095:
        return 0.30
    return 0.15
