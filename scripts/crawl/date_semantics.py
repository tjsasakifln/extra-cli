"""Contract date semantics validators.

Helps detect mixed/legacy publication dates and anomalies after the
dataAssinatura → data_publicacao mapping bug fix (migration 051).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _as_date(value: Any) -> date | None:
    """Coerce ISO string / date / datetime to ``date``, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s == "None":
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def validate_contract_dates(
    row: dict[str, Any],
    *,
    query_start: date | str | None = None,
    query_end: date | str | None = None,
    today: date | None = None,
) -> list[str]:
    """Return human-readable warning codes for a contract date row.

    Flags:
      - ``future_date``: any event/publication/assinatura date > today+1
      - ``assinatura_ne_publicacao``: assinatura and publicacao_fonte both set and differ
      - ``missing_all_dates``: no assinatura, publicacao_fonte, source_event, or legacy publicacao
      - ``outside_query_window``: source_event_date outside [query_start, query_end]
        when window bounds and a known event date are present

    Args:
        row: Normalized contract dict (transform output or DB-like mapping).
        query_start: Optional crawl window start (overrides row query_window_start).
        query_end: Optional crawl window end (overrides row query_window_end).
        today: Override "today" for deterministic tests.

    Returns:
        List of warning code strings (empty if clean).
    """
    warnings: list[str] = []
    ref_today = today or date.today()
    future_cutoff = ref_today + timedelta(days=1)

    data_assinatura = _as_date(row.get("data_assinatura"))
    data_publicacao_fonte = _as_date(row.get("data_publicacao_fonte"))
    source_event_date = _as_date(row.get("source_event_date"))
    data_publicacao = _as_date(row.get("data_publicacao"))  # legacy

    event = source_event_date or data_assinatura or data_publicacao_fonte or data_publicacao

    if event is None and data_assinatura is None and data_publicacao_fonte is None and data_publicacao is None:
        warnings.append("missing_all_dates")

    for label, d in (
        ("data_assinatura", data_assinatura),
        ("data_publicacao_fonte", data_publicacao_fonte),
        ("source_event_date", source_event_date),
        ("data_publicacao", data_publicacao),
    ):
        if d is not None and d > future_cutoff:
            warnings.append(f"future_date:{label}")
            break  # one future_date flag is enough

    if (
        data_assinatura is not None
        and data_publicacao_fonte is not None
        and data_assinatura != data_publicacao_fonte
    ):
        warnings.append("assinatura_ne_publicacao")

    qs = _as_date(query_start if query_start is not None else row.get("query_window_start"))
    qe = _as_date(query_end if query_end is not None else row.get("query_window_end"))
    semantics = (row.get("source_date_semantics") or "").strip()

    if event is not None and qs is not None and qe is not None and semantics and semantics != "unknown":
        if event < qs or event > qe:
            warnings.append("outside_query_window")

    return warnings
