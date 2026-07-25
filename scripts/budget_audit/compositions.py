"""Composition audit — structure and arithmetic only, no productivity judgments."""

from __future__ import annotations

from typing import Any

from scripts.budget_audit.materiality import MaterialityPolicy, classify_difference


def audit_compositions(
    compositions: list[dict[str, Any]],
    composition_inputs: list[dict[str, Any]],
    budget_items: list[dict[str, Any]],
    *,
    policy: MaterialityPolicy | None = None,
) -> dict[str, Any]:
    pol = policy or MaterialityPolicy()
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for inp in composition_inputs:
        if not inp.get("code"):
            issues.append(
                {
                    "kind": "INPUT_WITHOUT_CODE",
                    "input_id": inp.get("input_id"),
                    "cells": list((inp.get("source_cells") or {}).values()),
                }
            )
        if not inp.get("unit"):
            issues.append(
                {
                    "kind": "INPUT_WITHOUT_UNIT",
                    "input_id": inp.get("input_id"),
                    "cells": list((inp.get("source_cells") or {}).values()),
                }
            )
        coef = inp.get("coefficient")
        if coef is None:
            issues.append(
                {
                    "kind": "MISSING_COEFFICIENT",
                    "input_id": inp.get("input_id"),
                    "cells": list((inp.get("source_cells") or {}).values()),
                }
            )
        elif isinstance(coef, (int, float)) and coef < 0:
            issues.append(
                {
                    "kind": "NEGATIVE_COEFFICIENT",
                    "input_id": inp.get("input_id"),
                    "value": coef,
                    "cells": list((inp.get("source_cells") or {}).values()),
                }
            )
        if inp.get("unit_price") is None:
            issues.append(
                {
                    "kind": "MISSING_INPUT_PRICE",
                    "input_id": inp.get("input_id"),
                    "cells": list((inp.get("source_cells") or {}).values()),
                }
            )
        # coef * price = total
        if (
            isinstance(coef, (int, float))
            and isinstance(inp.get("unit_price"), (int, float))
            and isinstance(inp.get("total"), (int, float))
        ):
            recomputed = float(coef) * float(inp["unit_price"])
            result = classify_difference(float(inp["total"]), recomputed, policy=pol)
            checks.append(
                {
                    "check_id": f"comp:{inp.get('input_id')}:coef_x_price",
                    "formula_expected": "coefficient * unit_price = total",
                    "reported_value": inp["total"],
                    "recomputed_value": recomputed,
                    "status": result["status"],
                    "absolute_difference": result["absolute_difference"],
                    "source_cells": list((inp.get("source_cells") or {}).values()),
                }
            )

    # budget items without composition link (by code)
    input_codes = {str(i.get("code")) for i in composition_inputs if i.get("code")}
    for it in budget_items:
        code = it.get("code")
        if code and str(code) not in input_codes and compositions:
            # only flag if we have compositions sheet at all
            issues.append(
                {
                    "kind": "ITEM_WITHOUT_COMPOSITION",
                    "item_id": it.get("item_id"),
                    "code": code,
                    "cells": list((it.get("source_cells") or {}).values()),
                    "note": "No composition input row matched this code — may be structural",
                }
            )

    if compositions and not composition_inputs:
        issues.append(
            {
                "kind": "COMPOSITION_WITHOUT_INPUTS",
                "composition_ids": [c.get("composition_id") for c in compositions],
            }
        )

    return {
        "composition_count": len(compositions),
        "input_count": len(composition_inputs),
        "issue_count": len(issues),
        "check_count": len(checks),
        "issues": issues,
        "checks": checks,
        "policy": pol.to_dict(),
        "non_claims": [
            "Does not judge productivity as incorrect without comparable base",
            "Does not invent missing coefficients",
        ],
    }
