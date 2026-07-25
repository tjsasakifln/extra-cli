"""Arithmetic reconciliation and workbook integrity checks."""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.budget_audit.materiality import MaterialityPolicy, classify_difference


def audit_item_arithmetic(
    items: list[dict[str, Any]],
    *,
    policy: MaterialityPolicy | None = None,
) -> dict[str, Any]:
    pol = policy or MaterialityPolicy()
    checks: list[dict[str, Any]] = []

    for it in items:
        qty = it.get("quantity")
        # Prefer comparable pairs: sale×qty vs total_sale, else direct×qty vs total_direct
        unit_sale = it.get("unit_sale_price")
        unit_direct = it.get("unit_direct_cost")
        total_sale = it.get("total_sale_price")
        total_direct = it.get("total_direct_cost")

        source_cells = []
        sc = it.get("source_cells") or {}
        for k in ("quantity", "unit_sale_price", "total_sale_price", "unit_direct_cost", "total_direct_cost"):
            if sc.get(k):
                source_cells.append(sc[k])

        # Choose the consistent price/total pair (never mix direct unit with sale total)
        if qty is not None and unit_sale is not None and total_sale is not None:
            unit_price, total, pair = unit_sale, total_sale, "sale"
            formula_expected = "quantity * unit_sale_price = total_sale_price"
        elif qty is not None and unit_direct is not None and total_direct is not None:
            unit_price, total, pair = unit_direct, total_direct, "direct"
            formula_expected = "quantity * unit_direct_cost = total_direct_cost"
        elif qty is not None and unit_sale is not None and total_direct is not None and unit_direct is None:
            # only sale unit + total_direct available — not comparable
            unit_price, total, pair = None, None, "mixed_unavailable"
            formula_expected = "quantity * unit_price = total"
        elif qty is not None and unit_direct is not None and total_sale is not None and unit_sale is None:
            # direct unit vs sale total is a common false pairing — evaluate as NOT comparable
            # unless we also have bdi to bridge; otherwise NOT_EVALUATED with reason
            unit_price, total, pair = None, None, "direct_vs_sale_total"
            formula_expected = "quantity * unit_direct_cost ≠ total_sale without BDI bridge"
        else:
            unit_price, total, pair = (
                unit_sale if unit_sale is not None else unit_direct,
                total_sale if total_sale is not None else total_direct,
                "fallback",
            )
            formula_expected = "quantity * unit_price = total"

        if qty is None or unit_price is None or total is None or pair in {
            "mixed_unavailable",
            "direct_vs_sale_total",
        }:
            checks.append(
                {
                    "check_id": f"arith:{it.get('item_id')}:qty_x_pu",
                    "item_id": it.get("item_id"),
                    "formula_expected": formula_expected,
                    "formula_observed": None,
                    "reported_value": total_sale if total_sale is not None else total_direct,
                    "recomputed_value": None,
                    "status": "NOT_EVALUATED",
                    "reason": "missing_operands" if pair == "fallback" else pair,
                    "source_cells": source_cells,
                    "absolute_difference": None,
                    "relative_difference": None,
                    "tolerance": pol.absolute_tolerance_brl,
                }
            )
        else:
            recomputed = float(qty) * float(unit_price)
            result = classify_difference(float(total), recomputed, policy=pol)
            checks.append(
                {
                    "check_id": f"arith:{it.get('item_id')}:qty_x_pu",
                    "item_id": it.get("item_id"),
                    "formula_expected": formula_expected,
                    "formula_observed": f"{qty} * {unit_price} = {recomputed}",
                    "reported_value": total,
                    "recomputed_value": recomputed,
                    "status": result["status"],
                    "absolute_difference": result["absolute_difference"],
                    "relative_difference": result["relative_difference"],
                    "tolerance": result["tolerance"],
                    "severity_hint": result["severity_hint"],
                    "price_total_pair": pair,
                    "source_cells": source_cells,
                }
            )

        # unit_direct + BDI => sale if both present
        unit_direct = it.get("unit_direct_cost")
        bdi = it.get("bdi_pct")
        unit_sale = it.get("unit_sale_price")
        if unit_direct is not None and bdi is not None and unit_sale is not None:
            # Interpret BDI carefully:
            # if |bdi| <= 1 treat as fraction; if > 1 treat as percent points
            bdi_frac = float(bdi) if abs(float(bdi)) <= 1.0 else float(bdi) / 100.0
            # store interpretation
            expected_sale = float(unit_direct) * (1.0 + bdi_frac)
            result2 = classify_difference(float(unit_sale), expected_sale, policy=pol)
            checks.append(
                {
                    "check_id": f"arith:{it.get('item_id')}:direct_plus_bdi",
                    "item_id": it.get("item_id"),
                    "formula_expected": "unit_direct * (1 + bdi_frac) = unit_sale",
                    "formula_observed": f"{unit_direct} * (1 + {bdi_frac}) = {expected_sale}",
                    "bdi_interpretation": {
                        "raw": bdi,
                        "fraction_used": bdi_frac,
                        "rule": "abs<=1 => fraction else percent_points/100",
                    },
                    "reported_value": unit_sale,
                    "recomputed_value": expected_sale,
                    "status": result2["status"],
                    "absolute_difference": result2["absolute_difference"],
                    "relative_difference": result2["relative_difference"],
                    "tolerance": result2["tolerance"],
                    "severity_hint": result2["severity_hint"],
                    "source_cells": source_cells,
                }
            )

    status_counts = Counter(c["status"] for c in checks)
    return {
        "check_count": len(checks),
        "status_counts": dict(status_counts),
        "checks": checks,
        "policy": pol.to_dict(),
    }


def workbook_integrity(
    formulas: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    items: list[dict[str, Any]],
    hidden_content: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    findings_raw: list[dict[str, Any]] = []

    for f in formulas:
        st = f.get("formula_status")
        if st in {"BROKEN_REFERENCE", "EXTERNAL_REFERENCE", "MISSING_CACHE"}:
            findings_raw.append(
                {
                    "kind": st,
                    "sheet": f.get("sheet"),
                    "cells": [f"{f.get('sheet')}!{f.get('coordinate')}"],
                    "formula": f.get("formula"),
                    "cached_value": f.get("cached_value"),
                }
            )

    # negative qty/price
    for it in items:
        for field in ("quantity", "unit_sale_price", "unit_direct_cost", "total_sale_price"):
            val = it.get(field)
            if isinstance(val, (int, float)) and val < 0:
                findings_raw.append(
                    {
                        "kind": "NEGATIVE_VALUE",
                        "field": field,
                        "item_id": it.get("item_id"),
                        "sheet": it.get("sheet"),
                        "cells": list((it.get("source_cells") or {}).values()),
                        "value": val,
                    }
                )
        if it.get("unit") in (None, "") and it.get("description"):
            findings_raw.append(
                {
                    "kind": "MISSING_UNIT",
                    "item_id": it.get("item_id"),
                    "sheet": it.get("sheet"),
                    "cells": list((it.get("source_cells") or {}).values()),
                }
            )

    # duplicate codes
    codes = [it.get("code") for it in items if it.get("code")]
    code_counts = Counter(codes)
    for code, n in code_counts.items():
        if n > 1:
            affected = [it for it in items if it.get("code") == code]
            findings_raw.append(
                {
                    "kind": "DUPLICATE_CODE",
                    "code": code,
                    "count": n,
                    "item_ids": [a.get("item_id") for a in affected],
                    "cells": [
                        c
                        for a in affected
                        for c in (a.get("source_cells") or {}).values()
                    ],
                }
            )

    # duplicate item numbers
    nums = [str(it.get("item_number")) for it in items if it.get("item_number") is not None]
    for num, n in Counter(nums).items():
        if n > 1:
            findings_raw.append(
                {
                    "kind": "DUPLICATE_ITEM_NUMBER",
                    "item_number": num,
                    "count": n,
                }
            )

    hidden = hidden_content or []
    return {
        "formula_issues": [f for f in findings_raw if f.get("kind") in {
            "BROKEN_REFERENCE", "EXTERNAL_REFERENCE", "MISSING_CACHE"
        }],
        "value_issues": [f for f in findings_raw if f.get("kind") in {
            "NEGATIVE_VALUE", "MISSING_UNIT"
        }],
        "duplication_issues": [f for f in findings_raw if f.get("kind") in {
            "DUPLICATE_CODE", "DUPLICATE_ITEM_NUMBER"
        }],
        "hidden_content_count": len(hidden),
        "hidden_content": hidden,
        "all_issues": findings_raw,
        "issue_count": len(findings_raw),
    }


def audit_quantities(items: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    qtys = [it["quantity"] for it in items if isinstance(it.get("quantity"), (int, float))]
    mean = sum(qtys) / len(qtys) if qtys else None
    for it in items:
        q = it.get("quantity")
        if q is None:
            issues.append(
                {
                    "classification": "NEEDS_ENGINEER_REVIEW",
                    "kind": "MISSING_QUANTITY",
                    "item_id": it.get("item_id"),
                    "cells": list((it.get("source_cells") or {}).values()),
                }
            )
        elif isinstance(q, (int, float)) and q == 0:
            issues.append(
                {
                    "classification": "NEEDS_ENGINEER_REVIEW",
                    "kind": "ZERO_QUANTITY",
                    "item_id": it.get("item_id"),
                    "cells": list((it.get("source_cells") or {}).values()),
                }
            )
        elif isinstance(q, (int, float)) and q < 0:
            issues.append(
                {
                    "classification": "CONFIRMED_ARITHMETIC_ERROR",
                    "kind": "NEGATIVE_QUANTITY",
                    "item_id": it.get("item_id"),
                    "value": q,
                    "cells": list((it.get("source_cells") or {}).values()),
                }
            )
        elif mean and isinstance(q, (int, float)) and mean > 0 and q > mean * 50:
            issues.append(
                {
                    "classification": "OUTLIER",
                    "kind": "QUANTITY_OUTLIER",
                    "item_id": it.get("item_id"),
                    "value": q,
                    "mean": mean,
                    "cells": list((it.get("source_cells") or {}).values()),
                }
            )

    # same code different qty
    by_code: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        if it.get("code"):
            by_code.setdefault(str(it["code"]), []).append(it)
    for code, group in by_code.items():
        qtys_g = {g.get("quantity") for g in group}
        if len(qtys_g) > 1:
            issues.append(
                {
                    "classification": "CROSS_DOCUMENT_DIVERGENCE",
                    "kind": "SAME_CODE_DIFFERENT_QTY",
                    "code": code,
                    "values": list(qtys_g),
                    "item_ids": [g.get("item_id") for g in group],
                }
            )

    return {"issue_count": len(issues), "issues": issues}


def audit_abc(
    items: list[dict[str, Any]],
    *,
    a_threshold: float = 80.0,
    b_threshold: float = 95.0,
) -> dict[str, Any]:
    """Compute ABC curve from budget items by total_sale_price."""
    priced = []
    for it in items:
        total = it.get("total_sale_price")
        if total is None:
            total = it.get("total_direct_cost")
        if isinstance(total, (int, float)):
            priced.append({**it, "_total": float(total)})
    priced.sort(key=lambda x: x["_total"], reverse=True)
    grand = sum(x["_total"] for x in priced)
    abc = []
    running = 0.0
    for it in priced:
        running += it["_total"]
        share = (it["_total"] / grand * 100.0) if grand else 0.0
        cum = (running / grand * 100.0) if grand else 0.0
        if cum <= a_threshold:
            klass = "A"
        elif cum <= b_threshold:
            klass = "B"
        else:
            klass = "C"
        abc.append(
            {
                "item_id": it.get("item_id"),
                "code": it.get("code"),
                "description": it.get("description"),
                "total": it["_total"],
                "share_pct": share,
                "cumulative_pct": cum,
                "class": klass,
                "rule": f"A<={a_threshold}% B<={b_threshold}% else C",
                "source_cells": list((it.get("source_cells") or {}).values()),
            }
        )
    return {
        "item_count": len(abc),
        "grand_total": grand,
        "class_counts": dict(Counter(x["class"] for x in abc)),
        "items": abc,
        "rule": {"a_threshold": a_threshold, "b_threshold": b_threshold},
        "note": "Class A indicates materiality, not error or overprice",
    }
