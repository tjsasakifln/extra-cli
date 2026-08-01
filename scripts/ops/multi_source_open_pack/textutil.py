"""Normalização de texto e datas com timezone explícito."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

# Brasil continental (SC) — horário oficial de licitações locais.
BR_TZ = ZoneInfo("America/Sao_Paulo")
UTC = UTC


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def digits_only(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def cnpj8(s: str | None) -> str | None:
    d = digits_only(s)
    if len(d) >= 8:
        return d[:8]
    return None


def excel_safe(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, (int, float, bool)):
        return v
    s = str(v)
    return "".join(ch for ch in s if ord(ch) >= 32 or ch in "\t\n\r")


def br_currency(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def br_date(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, datetime):
        return v.astimezone(BR_TZ).strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    raw = str(v)
    dt = parse_datetime(raw)
    if dt:
        return dt.astimezone(BR_TZ).strftime("%d/%m/%Y %H:%M")
    try:
        return date.fromisoformat(raw[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return raw[:16]


def parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    raw = str(v)[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_datetime(v: Any, *, default_tz: ZoneInfo | timezone = BR_TZ) -> datetime | None:
    """Parse datetime with explicit timezone. Naive values assume America/Sao_Paulo."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=default_tz)
        return v
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime.combine(v, time(23, 59, 59), tzinfo=default_tz)

    raw = str(v).strip()
    if not raw:
        return None

    # ISO with offset or Z
    cleaned = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=default_tz)
        return dt
    except ValueError:
        pass

    # date only
    try:
        d = date.fromisoformat(raw[:10])
        return datetime.combine(d, time(23, 59, 59), tzinfo=default_tz)
    except ValueError:
        return None


def business_days_between(start: date, end: date) -> int:
    """Count business days from start (exclusive of start if same day logic) to end inclusive of end remaining."""
    if end < start:
        return 0
    days = 0
    cur = start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def days_remaining(deadline: datetime | None, now: datetime) -> tuple[int | None, int | None, bool]:
    """Return (calendar_days, business_days, is_open) relative to now."""
    if deadline is None:
        return None, None, False  # unknown deadline is not proven open
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=BR_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BR_TZ)
    if deadline <= now:
        return 0, 0, False
    cal = (deadline.date() - now.date()).days
    # if same calendar day but hour remaining
    if cal == 0:
        return 0, 0 if now.weekday() >= 5 else 0, True
    biz = business_days_between(now.date(), deadline.date())
    return cal, biz, True


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(dt: datetime | None = None) -> str:
    d = dt or utc_now()
    return d.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def optional_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
