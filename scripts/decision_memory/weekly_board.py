"""Weekly B2G Decision Board — derived from PostgreSQL memory only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.decision_memory.db import require_client_id
from scripts.decision_memory.repository import DecisionMemoryRepository


def build_weekly_board(
    repo: DecisionMemoryRepository,
    *,
    client_id: str,
    cycle_id: str | None = None,
    as_of: datetime | None = None,
    lookback_days: int = 14,
) -> dict[str, Any]:
    """Assemble board sections strictly from DB projections."""
    client_id = require_client_id(client_id)
    as_of = as_of or datetime.now(UTC).replace(microsecond=0)
    window_start = as_of - timedelta(days=lookback_days)

    decisions = repo.list_decisions(client_id, limit=5000, current_only=True)
    actions = repo.list_actions(client_id, limit=5000, current_only=True)
    outcomes = repo.list_outcomes(client_id, limit=5000, current_only=True)
    history = repo.list_decisions(client_id, limit=5000, current_only=False)

    # Pending REVIEW decisions
    pending = [d for d in decisions if d.get("human_decision") == "REVIEW"]
    if cycle_id:
        pending_prev = [
            d
            for d in decisions
            if d.get("human_decision") == "REVIEW" and d.get("cycle_id") and d.get("cycle_id") != cycle_id
        ]
    else:
        pending_prev = pending

    now = as_of
    overdue: list[dict[str, Any]] = []
    due_soon: list[dict[str, Any]] = []
    horizon = now + timedelta(days=7)
    for a in actions:
        if a.get("status") not in {"OPEN", "IN_PROGRESS", "OVERDUE"}:
            continue
        due = a.get("due_at")
        if not due:
            continue
        due_dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
        item = {
            "event_id": a.get("event_id"),
            "opportunity_key": a.get("opportunity_key"),
            "description": a.get("description"),
            "owner": a.get("owner") or "OWNER_ABSENT",
            "due_at": a.get("due_at"),
            "status": a.get("status"),
            "criticality": a.get("criticality"),
        }
        if due_dt < now:
            overdue.append(item)
        elif due_dt <= horizon:
            due_soon.append(item)

    # Recurring opportunities already decided (appear in >1 cycle or multiple events)
    by_opp: dict[str, list[dict[str, Any]]] = {}
    for d in history:
        by_opp.setdefault(str(d["opportunity_key"]), []).append(d)
    recurring = []
    for key, evs in by_opp.items():
        cycles = {e.get("cycle_id") for e in evs if e.get("cycle_id")}
        if len(evs) > 1 or len(cycles) > 1:
            current = next((d for d in decisions if d["opportunity_key"] == key), evs[0])
            recurring.append(
                {
                    "opportunity_key": key,
                    "event_count": len(evs),
                    "cycles": sorted(c for c in cycles if c),
                    "current_decision": current.get("human_decision"),
                    "last_decided_at": current.get("decided_at"),
                }
            )

    # New outcomes since window
    new_outcomes = []
    for o in outcomes:
        obs = o.get("observed_at")
        if not obs:
            continue
        obs_dt = datetime.fromisoformat(str(obs).replace("Z", "+00:00"))
        if obs_dt >= window_start:
            new_outcomes.append(
                {
                    "event_id": o.get("event_id"),
                    "opportunity_key": o.get("opportunity_key"),
                    "outcome_type": o.get("outcome_type"),
                    "observed_at": o.get("observed_at"),
                    "temporal_integrity": o.get("temporal_integrity"),
                    "source": o.get("source"),
                }
            )

    # Divergences recommendation vs decision vs outcome
    divergences = []
    dec_map = {d["opportunity_key"]: d for d in decisions}
    out_map: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        out_map[str(o["opportunity_key"])] = o
    for key, d in dec_map.items():
        rec = d.get("system_recommendation")
        hum = d.get("human_decision")
        if rec and rec not in {"UNKNOWN", "NOT_PROVIDED"} and rec != hum:
            divergences.append(
                {
                    "opportunity_key": key,
                    "kind": "recommendation_vs_decision",
                    "system_recommendation": rec,
                    "human_decision": hum,
                }
            )
        o_opt = out_map.get(key)
        if o_opt is not None and o_opt.get("outcome_type") not in {None, "UNKNOWN"}:
            ot = o_opt["outcome_type"]
            if hum == "GO" and ot in {"LOSS", "NO_PARTICIPATION", "INELIGIBLE"}:
                divergences.append(
                    {
                        "opportunity_key": key,
                        "kind": "decision_vs_outcome",
                        "human_decision": hum,
                        "outcome_type": ot,
                    }
                )
            elif hum == "NO_GO" and ot == "WIN":
                divergences.append(
                    {
                        "opportunity_key": key,
                        "kind": "decision_vs_outcome",
                        "human_decision": hum,
                        "outcome_type": ot,
                    }
                )

    # Profile fields that blocked decisions (from payload / constraints / limitations)
    profile_blocks = []
    for d in decisions:
        for item in d.get("constraints_known") or []:
            if "profile" in str(item).lower() or "bloque" in str(item).lower():
                profile_blocks.append({"opportunity_key": d["opportunity_key"], "constraint": item})
        for item in d.get("data_limitations") or []:
            if "profile" in str(item).lower() or "pending" in str(item).lower():
                profile_blocks.append({"opportunity_key": d["opportunity_key"], "limitation": item})
        payload = d.get("payload") or {}
        if isinstance(payload, dict):
            for b in payload.get("profile_blocks") or []:
                profile_blocks.append({"opportunity_key": d["opportunity_key"], "block": b})

    # Deliberation questions for the meeting
    deliberation = []
    for d in pending_prev:
        deliberation.append(
            {
                "opportunity_key": d.get("opportunity_key"),
                "question": "Decisão ainda em REVIEW — deliberar GO ou NO_GO",
                "justification": d.get("justification"),
                "actor": d.get("actor"),
            }
        )
    for a in overdue:
        deliberation.append(
            {
                "opportunity_key": a.get("opportunity_key"),
                "question": f"Ação vencida: {a.get('description')}",
                "owner": a.get("owner"),
                "due_at": a.get("due_at"),
            }
        )
    for div in divergences:
        deliberation.append(
            {
                "opportunity_key": div.get("opportunity_key"),
                "question": f"Divergência {div.get('kind')} — revisar premissas",
                "detail": div,
            }
        )

    return {
        "schema_version": "decision-memory/weekly-board/1.0",
        "client_id": client_id,
        "cycle_id": cycle_id,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "source": "postgresql:dm_*",
        "sections": {
            "pending_decisions_prior_cycle": pending_prev,
            "actions_overdue": overdue,
            "actions_due_soon": due_soon,
            "recurring_opportunities_decided": recurring,
            "new_outcomes_since_last_board": new_outcomes,
            "divergences": divergences,
            "profile_fields_blocking": profile_blocks,
            "deliberation_questions": deliberation,
        },
        "counts": {
            "pending_decisions": len(pending_prev),
            "actions_overdue": len(overdue),
            "actions_due_soon": len(due_soon),
            "recurring": len(recurring),
            "new_outcomes": len(new_outcomes),
            "divergences": len(divergences),
            "deliberation_items": len(deliberation),
        },
        "non_claims": [
            "Board is a projection of recorded memory, not a prediction engine",
            "Empty sections mean no recorded facts, not zero market activity",
        ],
    }
