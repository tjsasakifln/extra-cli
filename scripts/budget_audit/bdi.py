"""BDI audit — arithmetic and structure only.

Never claims legal/illegal/abusive BDI without normative human review.
Never treats BDI as margin.
"""

from __future__ import annotations

from typing import Any

from scripts.budget_audit.materiality import MaterialityPolicy, classify_difference


def _as_fraction(
    raw: float,
    *,
    number_format: str | None = None,
    role: str = "generic",
) -> tuple[float, str]:
    """Interpret stored percentage carefully.

    Roles:
    - component: Brazilian BDI component cells almost always store *percent points*
      (3 = 3%, 0.97 = 0.97%). Excel percent-format cells are already fractions.
    - generic / item: abs<=1 → fraction (0.25 = 25%); abs>1 → percent points / 100.

    Never treats 25 as 2500%. Never treats Excel-percent 0.25 as 0.25%.
    """
    fmt = (number_format or "").lower()
    if "%" in fmt:
        # openpyxl already converted display percent to fraction
        return float(raw), "excel_percent_format"

    if role == "component":
        # Component rows on Brazilian sheets use percent points even when |raw| <= 1
        # (e.g. 0.97 means 0.97%, not 97%).
        return float(raw) / 100.0, "component_percent_points"

    if abs(raw) <= 1.0:
        return float(raw), "fraction_abs_le_1"
    return float(raw) / 100.0, "percent_points_gt_1"


def audit_bdi(
    bdi_components: list[dict[str, Any]],
    budget_items: list[dict[str, Any]] | None = None,
    *,
    policy: MaterialityPolicy | None = None,
    declared_total_pct: float | None = None,
) -> dict[str, Any]:
    pol = policy or MaterialityPolicy()
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    components_out: list[dict[str, Any]] = []

    names_seen: dict[str, int] = {}
    frac_sum = 0.0
    for comp in bdi_components:
        name = str(comp.get("original_name") or "")
        raw = comp.get("percentage")
        key = name.strip().lower()
        names_seen[key] = names_seen.get(key, 0) + 1
        if raw is None:
            issues.append(
                {
                    "kind": "MISSING_COMPONENT_PCT",
                    "component_id": comp.get("component_id"),
                    "classification": "MISSING_CONTEXT",
                    "cells": list((comp.get("source_cells") or {}).values()),
                }
            )
            continue
        frac, rule = _as_fraction(
            float(raw),
            number_format=comp.get("number_format"),
            role="component",
        )
        frac_sum += frac
        components_out.append(
            {
                **comp,
                "fraction": frac,
                "interpretation_rule": rule,
            }
        )
        if abs(float(raw)) > 100 and "%" not in str(comp.get("number_format") or ""):
            issues.append(
                {
                    "kind": "PERCENT_OUT_OF_SCALE",
                    "component_id": comp.get("component_id"),
                    "raw": raw,
                    "classification": "NEEDS_ENGINEER_REVIEW",
                    "cells": list((comp.get("source_cells") or {}).values()),
                }
            )

    for name, count in names_seen.items():
        if count > 1:
            issues.append(
                {
                    "kind": "DUPLICATE_COMPONENT",
                    "name": name,
                    "count": count,
                    "classification": "ARITHMETICALLY_INCONSISTENT",
                }
            )

    total_pct_points = frac_sum * 100.0
    if declared_total_pct is not None:
        decl_frac, decl_rule = _as_fraction(float(declared_total_pct), role="generic")
        result = classify_difference(decl_frac * 100.0, total_pct_points, policy=pol)
        checks.append(
            {
                "check_id": "bdi:sum_components_vs_declared",
                "formula_expected": "sum(components) = declared_total (simple sum — only if methodology is additive)",
                "formula_observed": f"sum={total_pct_points} declared={decl_frac * 100.0}",
                "reported_value": decl_frac * 100.0,
                "recomputed_value": total_pct_points,
                "status": result["status"],
                "absolute_difference": result["absolute_difference"],
                "methodology_note": "Simple sum used only as structural check; compound formulas require declared formula",
                "declared_interpretation": decl_rule,
            }
        )

    # Consistency: if component sum is wildly outside typical BDI band, flag for review
    if components_out and (total_pct_points < 0 or total_pct_points > 80):
        issues.append(
            {
                "kind": "COMPONENT_SUM_OUTSIDE_TYPICAL_BAND",
                "sum_percent_points": total_pct_points,
                "classification": "NEEDS_ENGINEER_REVIEW",
                "note": "Not a legal judgment — scale/interpretation or incomplete extraction may apply",
            }
        )

    double_bdi_suspects = []
    if budget_items:
        for it in budget_items:
            ud = it.get("unit_direct_cost")
            us = it.get("unit_sale_price")
            bdi = it.get("bdi_pct")
            if ud is None or us is None or bdi is None:
                continue
            # item-level bdi_pct uses generic scale (not component)
            bdi_frac, _ = _as_fraction(float(bdi), role="generic")
            # skip if bdi_pct looks like a price accidentally mapped
            if abs(float(bdi)) > 100 and abs(float(bdi)) > abs(float(ud or 0)):
                continue
            once = float(ud) * (1.0 + bdi_frac)
            twice = float(ud) * (1.0 + bdi_frac) * (1.0 + bdi_frac)
            d_once = abs(float(us) - once)
            d_twice = abs(float(us) - twice)
            if d_twice < d_once and d_twice <= pol.absolute_tolerance_brl * 10:
                double_bdi_suspects.append(
                    {
                        "item_id": it.get("item_id"),
                        "unit_direct": ud,
                        "unit_sale": us,
                        "bdi_frac": bdi_frac,
                        "once": once,
                        "twice": twice,
                        "cells": list((it.get("source_cells") or {}).values()),
                        "classification": "NEEDS_ENGINEER_REVIEW",
                        "kind": "POSSIBLE_DOUBLE_BDI",
                    }
                )
                issues.append(
                    {
                        "kind": "POSSIBLE_DOUBLE_BDI",
                        "item_id": it.get("item_id"),
                        "classification": "NEEDS_ENGINEER_REVIEW",
                        "cells": list((it.get("source_cells") or {}).values()),
                        "once": once,
                        "twice": twice,
                        "unit_sale": us,
                    }
                )

    blob = " ".join(str(c.get("original_name") or "").lower() for c in bdi_components)
    for label in ("lucro", "risco", "administração", "administracao", "tribut"):
        if bdi_components and label not in blob and label.rstrip("o") not in blob:
            issues.append(
                {
                    "kind": "COMPONENT_NOT_FOUND_BY_NAME",
                    "looked_for": label,
                    "classification": "MISSING_CONTEXT",
                    "note": "Name absence is not proof of omission",
                }
            )

    return {
        "component_count": len(bdi_components),
        "components": components_out,
        "sum_fraction": frac_sum,
        "sum_percent_points": total_pct_points,
        "checks": checks,
        "issues": issues,
        "double_bdi_suspects": double_bdi_suspects,
        "policy": pol.to_dict(),
        "claims_allowed": [
            "ARITHMETICALLY_CONSISTENT",
            "ARITHMETICALLY_INCONSISTENT",
            "OUTSIDE_DECLARED_REFERENCE",
            "MISSING_CONTEXT",
            "NEEDS_ENGINEER_REVIEW",
            "NEEDS_LEGAL_REVIEW",
        ],
        "non_claims": [
            "BDI legal",
            "BDI ilegal",
            "BDI correto",
            "BDI abusivo",
            "BDI conforme TCU",
            "BDI is margin",
        ],
    }


def audit_social_charges(
    charges: list[dict[str, Any]],
    *,
    policy: MaterialityPolicy | None = None,
) -> dict[str, Any]:
    pol = policy or MaterialityPolicy()
    issues: list[dict[str, Any]] = []
    components = []
    frac_sum = 0.0
    for c in charges:
        raw = c.get("percentage")
        if raw is None:
            issues.append(
                {
                    "kind": "MISSING_CHARGE_PCT",
                    "classification": "NEEDS_SPECIALIST_REVIEW",
                    "component_id": c.get("component_id"),
                }
            )
            continue
        # Social charges use same component scale convention as BDI components
        frac, rule = _as_fraction(
            float(raw),
            number_format=c.get("number_format"),
            role="component",
        )
        frac_sum += frac
        components.append({**c, "fraction": frac, "interpretation_rule": rule})
        if abs(float(raw)) > 100 and "%" not in str(c.get("number_format") or ""):
            issues.append(
                {
                    "kind": "PERCENT_OUT_OF_SCALE",
                    "raw": raw,
                    "classification": "NEEDS_SPECIALIST_REVIEW",
                    "cells": list((c.get("source_cells") or {}).values()),
                }
            )
    return {
        "component_count": len(charges),
        "components": components,
        "sum_fraction": frac_sum,
        "issues": issues,
        "policy": pol.to_dict(),
        "default_classification_without_tax_context": "NEEDS_SPECIALIST_REVIEW",
        "non_claims": ["Does not invent applicable tax rates"],
    }
