"""Open-opportunity status logic (radar). Never treat history as open."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from scripts.pseo.normalization import iso_date, parse_date

# Official statuses that mean NOT open
CLOSED_STATUS_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bencerrad",
        r"\bhomologad",
        r"\badjudicad",
        r"\brevogad",
        r"\banulad",
        r"\bcancelad",
        r"\bsuspens",
        r"\bdesert",
        r"\bfracassad",
        r"\binabilitad",
        r"\bconclu[ií]d",
        r"\bfechad",
        r"\binativ",
        r"\bexpirad",
    )
]

OPEN_STATUS_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\babert",
        r"\bpublicad",
        r"\bem\s+andamento",
        r"\bdivulgad",
        r"\brecebimento\s+de\s+proposta",
        r"\bhabilit",
    )
]

STATUS_OPEN = "aberta"
STATUS_CLOSED = "encerrada"
STATUS_SUSPENDED = "suspensa"
STATUS_REVOKED = "revogada"
STATUS_ANNULLED = "anulada"
STATUS_DESERT = "deserta_fracassada"
STATUS_HISTORICAL = "historico"
STATUS_UNKNOWN = "incerta"


def classify_bid_status(
    bid: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Return open-status decision for a single bid/opportunity row."""
    as_of = as_of or date.today()
    as_of_s = as_of.isoformat()
    status_raw = str(
        bid.get("situacao")
        or bid.get("status")
        or bid.get("situacao_compra")
        or bid.get("status_compra")
        or ""
    ).strip()
    end = parse_date(
        bid.get("data_encerramento")
        or bid.get("data_encerramento_proposta")
        or bid.get("data_fim_proposta")
    )
    reasons: list[str] = []
    bucket = STATUS_UNKNOWN

    # Explicit closed statuses
    for pat in CLOSED_STATUS_PATTERNS:
        if status_raw and pat.search(status_raw):
            if re.search(r"revogad", status_raw, re.I):
                bucket = STATUS_REVOKED
            elif re.search(r"anulad", status_raw, re.I):
                bucket = STATUS_ANNULLED
            elif re.search(r"suspens", status_raw, re.I):
                bucket = STATUS_SUSPENDED
            elif re.search(r"desert|fracassad", status_raw, re.I):
                bucket = STATUS_DESERT
            else:
                bucket = STATUS_CLOSED
            reasons.append(f"status_match:{status_raw[:60]}")
            break

    # Date gate: closed if end < as_of
    if end is not None and end < as_of:
        if bucket == STATUS_UNKNOWN:
            bucket = STATUS_CLOSED
        reasons.append(f"data_encerramento<{as_of_s}")

    # is_active flag
    if bid.get("is_active") is False:
        if bucket == STATUS_UNKNOWN:
            bucket = STATUS_CLOSED
        reasons.append("is_active=false")

    # Open only if not closed and (end >= as_of or end null with open status)
    is_open = False
    if bucket in {
        STATUS_CLOSED,
        STATUS_REVOKED,
        STATUS_ANNULLED,
        STATUS_SUSPENDED,
        STATUS_DESERT,
        STATUS_HISTORICAL,
    }:
        is_open = False
    elif end is not None and end >= as_of:
        # require not explicit closed; null status ok if date future
        if not any(p.search(status_raw) for p in CLOSED_STATUS_PATTERNS if status_raw):
            is_open = True
            bucket = STATUS_OPEN
            reasons.append(f"data_encerramento>={as_of_s}")
    elif end is None:
        # without end date: only open if explicit open status
        if status_raw and any(p.search(status_raw) for p in OPEN_STATUS_PATTERNS):
            is_open = True
            bucket = STATUS_OPEN
            reasons.append("open_status_without_end_date")
        else:
            bucket = STATUS_HISTORICAL if bucket == STATUS_UNKNOWN else bucket
            reasons.append("no_end_date_no_open_status")
            is_open = False
    else:
        is_open = False

    return {
        "is_open": is_open,
        "status_bucket": bucket,
        "status_raw": status_raw or None,
        "data_encerramento": iso_date(end) if end else iso_date(bid.get("data_encerramento")),
        "as_of": as_of_s,
        "timezone": "America/Sao_Paulo",
        "reasons": reasons,
        "uncertainty": end is None or (not status_raw and is_open),
    }


def filter_open_bids(
    bids: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Split bids into open vs not-open; return counts by bucket."""
    as_of = as_of or date.today()
    open_bids: list[dict[str, Any]] = []
    closed_bids: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for b in bids:
        decision = classify_bid_status(b, as_of=as_of)
        enriched = dict(b)
        enriched["open_decision"] = decision
        counts[decision["status_bucket"]] = counts.get(decision["status_bucket"], 0) + 1
        if decision["is_open"]:
            open_bids.append(enriched)
        else:
            closed_bids.append(enriched)
    counts["open_total"] = len(open_bids)
    counts["closed_total"] = len(closed_bids)
    return open_bids, closed_bids, counts


# Freshness policy for radar (hours)
RADAR_WARNING_HOURS = 24
RADAR_FAIL_HOURS = 72


def radar_freshness(
    data_as_of: str | date | None,
    *,
    now: date | datetime | None = None,
    source_unavailable: bool = False,
) -> dict[str, Any]:
    """Evaluate radar freshness against 24h warning / 72h fail policy.

    ``now`` must be wall-clock (or real collection time), NOT forced equal to
    ``data_as_of`` — otherwise age is always 0 and hard-fail never fires.
    """
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    if now is None:
        now_d = date.today()
        now_source = "wall_clock_date"
    elif isinstance(now, _dt):
        now_d = now.date() if now.tzinfo is None else now.astimezone(_tz.utc).date()
        now_source = "wall_clock_datetime"
    else:
        now_d = now
        now_source = "provided_date"

    d = parse_date(data_as_of) if not isinstance(data_as_of, date) else data_as_of
    if d is None:
        return {
            "status": "fail",
            "age_hours": None,
            "warning_hours": RADAR_WARNING_HOURS,
            "fail_hours": RADAR_FAIL_HOURS,
            "reason": "missing_data_as_of",
            "now_source": now_source,
        }
    # date-only age in hours (full days * 24); never pass now=data_as_of at call site
    age_hours = float((now_d - d).days * 24)
    if age_hours < 0:
        age_hours = 0.0
    if age_hours > RADAR_FAIL_HOURS and not source_unavailable:
        status = "fail"
    elif age_hours > RADAR_WARNING_HOURS:
        status = "warning"
    else:
        status = "ok"
    if source_unavailable and status == "fail":
        status = "warning"
        reason = "source_unavailable_documented"
    else:
        reason = f"age_hours={age_hours}"
    return {
        "status": status,
        "age_hours": age_hours,
        "warning_hours": RADAR_WARNING_HOURS,
        "fail_hours": RADAR_FAIL_HOURS,
        "reason": reason,
        "source_unavailable": source_unavailable,
        "now_source": now_source,
        "data_as_of": d.isoformat() if hasattr(d, "isoformat") else str(d),
        "evaluated_at": now_d.isoformat(),
    }
