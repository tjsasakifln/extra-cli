"""Exequibility risk signals — never invent internal costs or margins."""

from __future__ import annotations

from typing import Any

from scripts.budget_audit.case_store import utc_now


def build_risk_register(
    *,
    findings: dict[str, Any],
    bdi: dict[str, Any] | None = None,
    compositions: dict[str, Any] | None = None,
    arithmetic: dict[str, Any] | None = None,
    abc: dict[str, Any] | None = None,
    internal_cost_provided: bool = False,
    min_margin_from_extra: float | None = None,
) -> dict[str, Any]:
    risks: list[dict[str, Any]] = []

    for f in findings.get("findings") or []:
        if f.get("severity") in {"CRITICAL", "HIGH"} and f.get("classification") == "ARITHMETIC_ERROR":
            risks.append(
                {
                    "risk_id": f"R-{len(risks)+1:04d}",
                    "signal": "OBJECTIVE_ERROR",
                    "title": f.get("title"),
                    "source_finding": f.get("finding_id"),
                    "cells": f.get("cells"),
                    "note": "Arithmetic objective error is not by itself inexequibility",
                }
            )
        if f.get("classification") == "BDI_INCONSISTENCY":
            risks.append(
                {
                    "risk_id": f"R-{len(risks)+1:04d}",
                    "signal": "TECHNICAL_ALERT",
                    "title": "BDI inconsistency signal",
                    "source_finding": f.get("finding_id"),
                    "cells": f.get("cells"),
                }
            )
        if f.get("classification") == "COMPOSITION_GAP":
            risks.append(
                {
                    "risk_id": f"R-{len(risks)+1:04d}",
                    "signal": "TECHNICAL_ALERT",
                    "title": "Composition gap",
                    "source_finding": f.get("finding_id"),
                    "cells": f.get("cells"),
                }
            )

    if bdi and bdi.get("double_bdi_suspects"):
        for s in bdi["double_bdi_suspects"]:
            risks.append(
                {
                    "risk_id": f"R-{len(risks)+1:04d}",
                    "signal": "TECHNICAL_ALERT",
                    "title": "Possible double BDI application",
                    "detail": s,
                    "classification": "NEEDS_ENGINEER_REVIEW",
                }
            )

    if not internal_cost_provided:
        risks.append(
            {
                "risk_id": f"R-{len(risks)+1:04d}",
                "signal": "NEEDS_INTERNAL_COST_DATA",
                "title": "Real margin not computed",
                "note": "Without Extra internal costs, system does not calculate real margin",
            }
        )

    if min_margin_from_extra is not None:
        risks.append(
            {
                "risk_id": f"R-{len(risks)+1:04d}",
                "signal": "COMMERCIAL_RISK",
                "title": "Extra minimum margin provided as scenario",
                "scenario": {
                    "input_source": "EXTRA_EXPLICIT",
                    "assumption": f"min_margin={min_margin_from_extra}",
                    "not_observed_fact": True,
                },
            }
        )

    if abc and abc.get("items"):
        top = [x for x in abc["items"] if x.get("class") == "A"][:5]
        risks.append(
            {
                "risk_id": f"R-{len(risks)+1:04d}",
                "signal": "HYPOTHESIS",
                "title": "Class A material items for focused review",
                "items": [
                    {"item_id": t.get("item_id"), "share_pct": t.get("share_pct")}
                    for t in top
                ],
                "note": "Class A is materiality, not error",
            }
        )

    return {
        "generated_at": utc_now(),
        "risk_count": len(risks),
        "risks": risks,
        "non_claims": [
            "Does not conclude inexequibility",
            "Does not invent internal cost",
            "Does not invent win probability",
            "Does not suggest optimal bid",
            "Does not treat BDI as margin",
        ],
    }
