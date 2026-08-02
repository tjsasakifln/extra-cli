"""Honest metrics with transparent numerators, denominators, and unknowns."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from scripts.decision_memory.db import require_client_id
from scripts.decision_memory.models import MetricCell
from scripts.decision_memory.repository import DecisionMemoryRepository

# Causal metrics that must NEVER be auto-computed as factual influence.
FORBIDDEN_AUTO_CAUSAL = frozenset(
    {
        "decision_influence_rate",
        "loss_avoided",
        "causal_win_attribution",
        "confenge_caused_win",
    }
)


def compute_metrics(
    repo: DecisionMemoryRepository,
    *,
    client_id: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    client_id = require_client_id(client_id)
    decisions = repo.list_decisions(client_id, limit=10000, current_only=True)
    actions = repo.list_actions(client_id, limit=10000, current_only=True)
    outcomes = repo.list_outcomes(client_id, limit=10000, current_only=True)

    def in_period(ts: str | None) -> bool:
        if period_start is None and period_end is None:
            return True
        if not ts:
            return False
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if period_start and dt < period_start:
            return False
        if period_end and dt > period_end:
            return False
        return True

    decs = [d for d in decisions if in_period(d.get("decided_at"))]
    acts = [a for a in actions if in_period(a.get("created_at") or a.get("due_at"))]
    outs = [o for o in outcomes if in_period(o.get("observed_at"))]

    n_eval = len(decs)
    by_decision = {"GO": 0, "REVIEW": 0, "NO_GO": 0}
    for d in decs:
        hd = d.get("human_decision")
        if hd in by_decision:
            by_decision[hd] += 1

    # Outcomes by type
    out_by_type: dict[str, int] = {}
    for o in outs:
        t = str(o.get("outcome_type") or "UNKNOWN")
        out_by_type[t] = out_by_type.get(t, 0) + 1

    # Opportunities with any outcome vs unknown
    opp_decided = {d["opportunity_key"] for d in decs}
    opp_with_outcome = {o["opportunity_key"] for o in outs if o.get("outcome_type") != "UNKNOWN"}
    unknown_outcomes = len(opp_decided - opp_with_outcome)

    # Win rate: WIN / (WIN + LOSS) — denominator explicit; unknowns excluded from denom
    wins = out_by_type.get("WIN", 0)
    losses = out_by_type.get("LOSS", 0)
    decided_bid_denom = wins + losses
    win_rate = (wins / decided_bid_denom) if decided_bid_denom else None

    # Ineligibility rate among submitted-like outcomes
    submittedish = (
        out_by_type.get("PROPOSAL_SUBMITTED", 0)
        + out_by_type.get("INELIGIBLE", 0)
        + out_by_type.get("DISQUALIFIED", 0)
        + wins
        + losses
    )
    ineligible = out_by_type.get("INELIGIBLE", 0) + out_by_type.get("DISQUALIFIED", 0)
    inelig_rate = (ineligible / submittedish) if submittedish else None

    # Actions
    open_a = sum(1 for a in acts if a.get("status") in {"OPEN", "IN_PROGRESS", "OVERDUE"})
    completed_a = sum(1 for a in acts if a.get("status") == "COMPLETED")
    overdue_a = 0
    now = datetime.now().astimezone()
    for a in acts:
        if a.get("status") in {"OPEN", "IN_PROGRESS"} and a.get("due_at"):
            due = datetime.fromisoformat(str(a["due_at"]).replace("Z", "+00:00"))
            if due < now:
                overdue_a += 1

    # Divergences
    rec_div = 0
    rec_known = 0
    for d in decs:
        rec = d.get("system_recommendation")
        hum = d.get("human_decision")
        if rec and rec not in {"UNKNOWN", "NOT_PROVIDED", None}:
            rec_known += 1
            if rec != hum:
                rec_div += 1

    # Decision vs outcome divergence (GO + LOSS, NO_GO + WIN, etc.) — descriptive only
    dec_by_opp = {d["opportunity_key"]: d for d in decs}
    dec_out_div = 0
    paired = 0
    for o in outs:
        d_opt = dec_by_opp.get(o["opportunity_key"])
        if not d_opt or o.get("outcome_type") in {None, "UNKNOWN"}:
            continue
        paired += 1
        hum = d_opt.get("human_decision")
        ot = o.get("outcome_type")
        if hum == "GO" and ot in {"LOSS", "NO_PARTICIPATION", "INELIGIBLE", "DISQUALIFIED"}:
            dec_out_div += 1
        elif hum == "NO_GO" and ot == "WIN":
            dec_out_div += 1

    # Margin: only when provided
    margins_exp = [float(o["expected_margin"]) for o in outs if o.get("expected_margin") is not None]
    margins_real = [float(o["realized_margin"]) for o in outs if o.get("realized_margin") is not None]

    cells = [
        MetricCell(
            name="opportunities_evaluated",
            numerator=n_eval,
            denominator=None,
            unknown_count=0,
            limitations=["Counts current decision projection only"],
        ),
        MetricCell(name="decisions_go", numerator=by_decision["GO"], denominator=n_eval or None),
        MetricCell(name="decisions_review", numerator=by_decision["REVIEW"], denominator=n_eval or None),
        MetricCell(name="decisions_no_go", numerator=by_decision["NO_GO"], denominator=n_eval or None),
        MetricCell(
            name="outcomes_unknown",
            numerator=unknown_outcomes,
            denominator=n_eval or None,
            unknown_count=unknown_outcomes,
            limitations=["Absence of outcome is UNKNOWN, never LOSS or zero"],
        ),
        MetricCell(
            name="win_rate",
            numerator=wins,
            denominator=decided_bid_denom if decided_bid_denom else None,
            value=win_rate,
            unknown_count=unknown_outcomes,
            limitations=[
                "Denominator is WIN+LOSS only; UNKNOWN and non-participation excluded",
                "Not causal; does not prove decision quality",
            ],
        ),
        MetricCell(
            name="ineligibility_rate",
            numerator=ineligible,
            denominator=submittedish if submittedish else None,
            value=inelig_rate,
            limitations=["Denominator is submitted-like outcomes only"],
        ),
        MetricCell(name="actions_open", numerator=open_a, denominator=len(acts) or None),
        MetricCell(name="actions_completed", numerator=completed_a, denominator=len(acts) or None),
        MetricCell(name="actions_overdue", numerator=overdue_a, denominator=open_a or None),
        MetricCell(
            name="recommendation_decision_divergence",
            numerator=rec_div,
            denominator=rec_known if rec_known else None,
            limitations=["Only where system_recommendation was provided"],
        ),
        MetricCell(
            name="decision_outcome_divergence_descriptive",
            numerator=dec_out_div,
            denominator=paired if paired else None,
            limitations=[
                "Descriptive pairing only — not causal influence",
                "decision_influence_rate is forbidden as auto-computed factual metric",
            ],
        ),
        MetricCell(
            name="margin_expected_declared_count",
            numerator=len(margins_exp),
            denominator=len(outs) or None,
            unknown_count=len(outs) - len(margins_exp),
            limitations=["Margins only when explicitly provided by valid source"],
        ),
        MetricCell(
            name="margin_realized_declared_count",
            numerator=len(margins_real),
            denominator=len(outs) or None,
            unknown_count=len(outs) - len(margins_real),
            limitations=["Margins only when explicitly provided by valid source"],
        ),
    ]

    return {
        "ok": True,
        "client_id": client_id,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "metrics": [c.model_dump(mode="json") for c in cells],
        "outcome_type_counts": out_by_type,
        "forbidden_auto_causal": sorted(FORBIDDEN_AUTO_CAUSAL),
        "non_claims": [
            "Metrics do not prove CONFENGE caused a win",
            "Missing outcomes are UNKNOWN, not defeats",
            "decision_influence_rate requires human-founded counterfactual (not auto)",
        ],
    }
