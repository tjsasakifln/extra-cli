"""Versioned unit normalization dictionary.

Never auto-converts dimensionally incompatible units.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from scripts.budget_audit.constants import UNITS_DICT_VERSION

# canonical_unit -> aliases (lowercase, stripped)
_UNIT_ALIASES: dict[str, tuple[str, ...]] = {
    "m": ("m", "metro", "metros", "ml", "m.l.", "m.l"),
    "m²": ("m2", "m²", "m^2", "metro2", "metros2", "m².", "m2."),
    "m³": ("m3", "m³", "m^3", "metro3", "metros3", "m³.", "m3."),
    "kg": ("kg", "quilo", "quilos", "kilograma", "kilogramas"),
    "t": ("t", "ton", "tonelada", "toneladas"),
    "h": ("h", "hr", "hora", "horas", "hh"),
    "h·equip": ("h.equip", "h·equip", "he", "h-equip", "hora equipamento"),
    "un": ("un", "und", "unid", "unidade", "unidades", "pç", "pc", "peca", "peça"),
    "cj": ("cj", "conj", "conjunto", "conjuntos"),
    "vb": ("vb", "verba", "glb", "global"),
    "mês": ("mes", "mês", "meses", "mensal"),
    "dia": ("dia", "dias", "d"),
    "km": ("km", "quilometro", "quilômetros", "quilometros"),
    "tkm": ("tkm", "t.km", "t×km", "txkm"),
    "L": ("l", "lt", "litro", "litros"),
    "%": ("%", "pct", "percent", "percentual"),
}

# Build reverse map
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canon, aliases in _UNIT_ALIASES.items():
    for a in aliases:
        _ALIAS_TO_CANONICAL[a.lower().strip()] = canon


@dataclass
class NormalizedUnit:
    original: str | None
    normalized: str | None
    rule: str
    confidence: float
    dict_version: str = UNITS_DICT_VERSION
    convertible_to: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_unit(raw: str | None) -> NormalizedUnit:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return NormalizedUnit(
            original=raw if isinstance(raw, str) else None,
            normalized=None,
            rule="EMPTY",
            confidence=0.0,
        )
    text = str(raw).strip()
    key = text.lower()
    # collapse whitespace
    key = re.sub(r"\s+", " ", key)
    if key in _ALIAS_TO_CANONICAL:
        return NormalizedUnit(
            original=text,
            normalized=_ALIAS_TO_CANONICAL[key],
            rule="ALIAS_EXACT",
            confidence=1.0,
        )
    # try without trailing dots
    key2 = key.rstrip(".")
    if key2 in _ALIAS_TO_CANONICAL:
        return NormalizedUnit(
            original=text,
            normalized=_ALIAS_TO_CANONICAL[key2],
            rule="ALIAS_STRIP_DOT",
            confidence=0.95,
        )
    return NormalizedUnit(
        original=text,
        normalized=None,
        rule="UNKNOWN",
        confidence=0.0,
    )


def units_compatible(a: str | None, b: str | None) -> bool:
    """True only if both normalize to same canonical unit."""
    na = normalize_unit(a)
    nb = normalize_unit(b)
    if na.normalized is None or nb.normalized is None:
        return False
    return na.normalized == nb.normalized


def forbid_auto_conversion(from_unit: str | None, to_unit: str | None) -> bool:
    """Return True if conversion would be dimensionally unsafe without explicit factor."""
    if units_compatible(from_unit, to_unit):
        return False
    return True


def unit_dictionary() -> dict[str, Any]:
    return {
        "version": UNITS_DICT_VERSION,
        "canonical_units": sorted(_UNIT_ALIASES.keys()),
        "aliases": {k: list(v) for k, v in _UNIT_ALIASES.items()},
        "forbidden_auto_conversions": [
            "m² → m",
            "kg → t without explicit factor",
            "m³ → kg without density",
            "vb → un",
        ],
    }
