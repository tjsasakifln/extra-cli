"""Neutralize formula injection on export of textual fields."""

from __future__ import annotations

from typing import Any

_INJECTION_PREFIXES = ("=", "+", "-", "@")


def neutralize_formula_injection(value: Any, *, is_formula: bool = False) -> Any:
    """Prefix dangerous leading characters in text that is not a legitimate formula.

    Excel/LibreOffice treat cells starting with = + - @ as formulas.
    For export of model text fields we neutralize unless is_formula=True.
    """
    if is_formula:
        return value
    if value is None:
        return value
    if not isinstance(value, str):
        return value
    if not value:
        return value
    stripped = value.lstrip()
    if stripped and stripped[0] in _INJECTION_PREFIXES:
        return "'" + value
    return value


def safe_cell_value(value: Any) -> Any:
    """Apply neutralization for spreadsheet export."""
    return neutralize_formula_injection(value, is_formula=False)
