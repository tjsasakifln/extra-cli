"""Materiality and tolerance policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.budget_audit.constants import DEFAULT_MATERIALITY


@dataclass(frozen=True)
class MaterialityPolicy:
    absolute_tolerance_brl: float = DEFAULT_MATERIALITY["absolute_tolerance_brl"]
    relative_tolerance_pct: float = DEFAULT_MATERIALITY["relative_tolerance_pct"]
    rounding_tolerance: float = DEFAULT_MATERIALITY["rounding_tolerance"]
    materiality_brl: float = DEFAULT_MATERIALITY["materiality_brl"]
    materiality_pct_of_total: float = DEFAULT_MATERIALITY["materiality_pct_of_total"]

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MaterialityPolicy:
        if not data:
            return cls()
        kwargs: dict[str, float] = {}
        for key in asdict(cls()).keys():
            if key in data and data[key] is not None:
                kwargs[key] = float(data[key])
        return cls(**kwargs)


def classify_difference(
    reported: float | None,
    recomputed: float | None,
    *,
    policy: MaterialityPolicy | None = None,
    total_budget: float | None = None,
) -> dict[str, Any]:
    """Compare reported vs recomputed and return status + metrics.

    Never treats missing cache as zero — caller must pass None for missing.
    """
    pol = policy or MaterialityPolicy()
    if reported is None or recomputed is None:
        return {
            "status": "NOT_EVALUATED",
            "absolute_difference": None,
            "relative_difference": None,
            "tolerance": pol.absolute_tolerance_brl,
            "severity_hint": "INFO",
        }

    abs_diff = abs(float(reported) - float(recomputed))
    base = max(abs(float(reported)), abs(float(recomputed)), 1e-12)
    rel_diff = (abs_diff / base) * 100.0

    if abs_diff <= pol.absolute_tolerance_brl or abs_diff <= pol.rounding_tolerance:
        status = "PASS"
        severity = "INFO"
    elif abs_diff <= pol.materiality_brl and rel_diff <= pol.relative_tolerance_pct:
        status = "ROUNDING_DIFFERENCE"
        severity = "LOW"
    else:
        material_by_total = False
        if total_budget and total_budget > 0:
            material_by_total = (abs_diff / total_budget) * 100.0 >= pol.materiality_pct_of_total
        if abs_diff >= pol.materiality_brl or material_by_total or rel_diff > pol.relative_tolerance_pct:
            status = "MATERIAL_DIFFERENCE"
            severity = "HIGH" if abs_diff >= pol.materiality_brl else "MEDIUM"
        else:
            status = "ROUNDING_DIFFERENCE"
            severity = "LOW"

    return {
        "status": status,
        "absolute_difference": abs_diff,
        "relative_difference": rel_diff,
        "tolerance": pol.absolute_tolerance_brl,
        "severity_hint": severity,
        "reported_value": reported,
        "recomputed_value": recomputed,
    }
