"""Text and unit normalization for acervo search (no I/O)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Canonical unit aliases (output unit is always canonical form used in store).
UNIT_ALIASES: dict[str, str] = {
    "m2": "m2",
    "m²": "m2",
    "m^2": "m2",
    "metro quadrado": "m2",
    "metros quadrados": "m2",
    "m3": "m3",
    "m³": "m3",
    "ml": "ml",
    "un": "un",
    "unid": "un",
    "unidade": "un",
    "unidades": "un",
}


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    t = strip_accents(str(text)).lower().strip()
    t = t.replace("ç", "c")
    t = re.sub(r"[^\w\s/+\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_unit(unit: str | None) -> str | None:
    if unit is None or str(unit).strip() == "":
        return None
    key = normalize_text(unit).replace(" ", "")
    # Restore common forms
    key = key.replace("m2", "m2").replace("metroquadrado", "m2")
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    raw = normalize_text(unit)
    return UNIT_ALIASES.get(raw, raw.replace(" ", ""))


def normalize_certificate_number(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9A-Za-z\-]", "", str(value)).strip()


def art_number_variants(art: str | None) -> set[str]:
    """Return comparable ART number variants (with/without hyphen)."""
    if not art:
        return set()
    raw = str(art).strip()
    digits = re.sub(r"[^0-9]", "", raw)
    variants = {normalize_text(raw), raw, digits}
    if len(digits) >= 2:
        # e.g. 93262060 -> 9326206-0
        variants.add(f"{digits[:-1]}-{digits[-1]}")
        variants.add(digits)
    return {v for v in variants if v}


def quantity_close(a: float | None, b: float | None, tol: float = 0.01) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def item_service_blob(item: dict[str, Any]) -> str:
    parts = [
        item.get("service") or "",
        item.get("original_description") or "",
        item.get("activity") or "",
        " ".join(item.get("qualifiers") or []),
    ]
    return normalize_text(" ".join(parts))
