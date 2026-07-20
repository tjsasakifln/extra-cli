"""Strategic ranking decisions for DeepSeek CTO.

DeepSeek may only return:
  ACCEPT_TOP | RECOMPUTE | ESCALATE | NOOP

It cannot silently pick ranking[1], invent features, or edit DoD criteria.
After ACCEPT_TOP the squad force-next / ranking[0] path continues.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from scripts.cto.redaction import redact_obj

STRATEGIC_ACTIONS = frozenset({"ACCEPT_TOP", "RECOMPUTE", "ESCALATE", "NOOP"})
RECOMPUTE_CAUSES = frozenset(
    {
        "stale_state",
        "incorrect_dependency",
        "active_work_conflict",
        "new_factual_evidence",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_strategic_decision(data: dict[str, Any]) -> dict[str, Any]:
    action = data.get("action")
    if action not in STRATEGIC_ACTIONS:
        raise ValueError(f"invalid strategic action: {action!r}")
    if action == "ACCEPT_TOP":
        if not data.get("selected_id"):
            raise ValueError("ACCEPT_TOP requires selected_id == ranking[0]")
    if action == "RECOMPUTE":
        cause = data.get("recompute_cause")
        if cause not in RECOMPUTE_CAUSES:
            raise ValueError(f"RECOMPUTE requires objective cause in {sorted(RECOMPUTE_CAUSES)}")
        if not (data.get("reason") or "").strip():
            raise ValueError("RECOMPUTE requires short auditable reason")
    if action == "ESCALATE" and not (data.get("reason") or "").strip():
        raise ValueError("ESCALATE requires reason")
    # Forbid silent rank picking
    if data.get("selected_rank") not in (None, 0, 1) and action == "ACCEPT_TOP":
        # selected_rank must be 0 (1-based would be wrong); only ranking[0]
        if int(data.get("selected_rank") or 0) != 0:
            raise ValueError("ACCEPT_TOP cannot select ranking[n] for n!=0")
    out = {
        "schema_version": "1.0",
        "decision_id": data.get("decision_id") or f"strat-{uuid.uuid4().hex[:12]}",
        "cycle_id": data.get("cycle_id") or f"cyc-{_utc_now()}",
        "action": action,
        "selected_id": data.get("selected_id"),
        "selected_rank": 0 if action == "ACCEPT_TOP" else None,
        "reason": (data.get("reason") or "")[:2000],
        "recompute_cause": data.get("recompute_cause"),
        "confidence": float(data.get("confidence") or 0.0),
        "timestamp_utc": _utc_now(),
        # Never store chain-of-thought
        "inputs_hash": data.get("inputs_hash"),
        "api_usage": data.get("api_usage"),
    }
    return redact_obj(out)


def accept_top_from_ranking(
    ranking: dict[str, Any],
    *,
    cycle_id: str,
    reason: str = "Accept current ranking[0] from extra-dod-roi",
) -> dict[str, Any]:
    top = None
    top_list = ranking.get("top") or ranking.get("items") or []
    if top_list:
        top = top_list[0]
    selected = ranking.get("selected_id") or (top or {}).get("id")
    return validate_strategic_decision(
        {
            "cycle_id": cycle_id,
            "action": "ACCEPT_TOP" if selected else "NOOP",
            "selected_id": selected,
            "selected_rank": 0,
            "reason": reason if selected else "No ranking[0] available",
            "confidence": 0.8 if selected else 1.0,
        }
    )


def build_strategic_payload(
    *,
    dod_snapshot: dict[str, Any],
    gates: dict[str, Any],
    ranking: dict[str, Any],
    dependencies: list[Any] | None = None,
    blockers: list[Any] | None = None,
    active_prs: list[Any] | None = None,
    scope_conflicts: list[Any] | None = None,
    risk: str | None = None,
    cost_estimate: Any = None,
    expected_impact: str | None = None,
    evidence: list[Any] | None = None,
    commitments: list[Any] | None = None,
) -> dict[str, Any]:
    """Limited redacted payload for DeepSeek strategic CTO."""
    top = (ranking.get("top") or [])[:5]
    return redact_obj(
        {
            "role": "strategic_cto",
            "allowed_actions": sorted(STRATEGIC_ACTIONS),
            "rules": [
                "ACCEPT_TOP accepts ranking[0] only",
                "RECOMPUTE only for stale/dependency/conflict/new evidence",
                "Never select ranking[1+] silently",
                "Never invent features or edit DoD criteria",
                "Never authorize human-only actions",
            ],
            "dod_snapshot": dod_snapshot,
            "gates": gates,
            "ranking_top5": top,
            "ranking_selected_id": ranking.get("selected_id"),
            "ranking_stale": ranking.get("stale"),
            "dependencies": dependencies or [],
            "blockers": blockers or [],
            "active_prs": active_prs or [],
            "scope_conflicts": scope_conflicts or [],
            "risk": risk,
            "cost_estimate": cost_estimate,
            "expected_impact": expected_impact,
            "evidence": evidence or [],
            "commitments": commitments or [],
        }
    )
