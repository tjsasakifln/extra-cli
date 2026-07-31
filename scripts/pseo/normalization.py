"""Normalization helpers for public pSEO export (dates, text, money)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


def iso_date(v: Any) -> str | None:
    """Normalize to YYYY-MM-DD or None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if not s:
        return None
    # ISO datetime
    if "T" in s:
        s = s.split("T", 1)[0]
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # BR dd/mm/yyyy
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s[:10] if s else None


def iso_datetime(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.strftime("%Y-%m-%dT%H:%M:%SZ")
        return v.isoformat()
    s = str(v).strip()
    return s or None


def parse_date(v: Any) -> date | None:
    s = iso_date(v)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def slugify(text: str, max_len: int = 80) -> str:
    t = (text or "").lower()
    t = re.sub(r"[àáâãä]", "a", t)
    t = re.sub(r"[èéêë]", "e", t)
    t = re.sub(r"[ìíîï]", "i", t)
    t = re.sub(r"[òóôõö]", "o", t)
    t = re.sub(r"[ùúûü]", "u", t)
    t = re.sub(r"[ç]", "c", t)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:max_len].strip("-") or "item"


def cnpj8(cnpj: str | None) -> str:
    d = re.sub(r"\D", "", cnpj or "")
    return d[:8] if len(d) >= 8 else d


def cnpj14(cnpj: str | None) -> str:
    return re.sub(r"\D", "", cnpj or "")[:14]


def collapse_ws(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def money_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
