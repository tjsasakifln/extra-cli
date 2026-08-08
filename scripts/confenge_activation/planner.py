"""Commercial activation planner: universe → projections → capacity-aware hot set."""

from __future__ import annotations

import resource
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from scripts.confenge_activation.funnel import (
    DOWNSTREAM_PENDING,
    DOWNSTREAM_SELECTED,
    apply_commercial_memory,
    is_reeligible,
    priority_band_for,
)
from scripts.confenge_activation.models import (
    ActivationCycleResult,
    ActivationProjection,
    stable_hash,
)
from scripts.confenge_activation.policy import ActivationPolicy, load_policy
from scripts.confenge_activation.score import compute_activation_score
from scripts.confenge_activation.triggers import detect_triggers


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _peak_rss_mb() -> float | None:
    try:
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)
    except Exception:  # noqa: BLE001
        return None


def _digits_cnpj(row: dict[str, Any]) -> str:
    raw = str(row.get("cnpj14") or row.get("cnpj") or "")
    d = "".join(ch for ch in raw if ch.isdigit())
    return d if len(d) == 14 else ""


def source_hash_for_row(row: dict[str, Any]) -> str:
    """Hash of observational fields that drive activation (not rank alone)."""
    port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    payload = {
        "cnpj14": _digits_cnpj(row),
        "last_contract_date": port.get("last_contract_date"),
        "first_contract_date": port.get("first_contract_date"),
        "active_contract_count": port.get("active_contract_count"),
        "contract_count_recent": port.get("contract_count_recent"),
        "contract_count_total": port.get("contract_count_total"),
        "value_recent_brl": port.get("value_recent_brl"),
        "value_total_brl": port.get("value_total_brl"),
        "recent_contracts": port.get("recent_contracts") or [],
        "outreach_eligibility": row.get("outreach_eligibility"),
        "commercial_state": row.get("commercial_state"),
        "construction_sector_fit": (
            (row.get("construction_evidence") or {}).get("sector_fit")
            if isinstance(row.get("construction_evidence"), dict)
            else None
        ),
        "new_process_document": row.get("new_process_document"),
    }
    return stable_hash(payload)


def _commercial_state(row: dict[str, Any], prior: dict[str, Any] | None) -> str:
    for src in (row, prior or {}):
        st = str(src.get("commercial_state") or "").upper()
        if st:
            return st
    elig = str(row.get("outreach_eligibility") or "").upper()
    if elig in {"DNC", "DO_NOT_CONTACT"}:
        return "DO_NOT_CONTACT"
    return "NEW"


def _decide_state(
    *,
    commercial_state: str,
    fired: list[Any],
    policy: ActivationPolicy,
    score: float,
) -> tuple[str, list[str]]:
    if commercial_state in policy.suppressed_states:
        return "SUPPRESSED", ["HUMAN_SUPPRESSED", commercial_state]

    # Active commercial blocks: not cold ACTIONABLE_NOW
    if commercial_state in policy.active_commercial_block:
        codes = [f.code for f in fired] if fired else ["ACTIVE_CADENCE_OR_HUMAN"]
        return "WATCH", codes

    if not fired:
        return "WATCH", []

    # Highest promotion among fired
    order = {"ACTIONABLE_NOW": 3, "RESEARCH_REQUIRED": 2, "WATCH": 1, "SUPPRESSED": 0}
    best_state = "WATCH"
    codes: list[str] = []
    for f in fired:
        codes.append(f.code)
        if order.get(f.promotes_to, 0) > order.get(best_state, 0):
            best_state = f.promotes_to

    if best_state == "ACTIONABLE_NOW" and score < policy.hot_set_min_score * 0.5:
        # Weak score with actionable trigger → research first
        return "RESEARCH_REQUIRED", codes

    return best_state, codes


def _next_best_action(
    state: str,
    fired: list[Any],
    *,
    as_of: date,
    policy: ActivationPolicy,
    evaluated_at: str,
) -> str | None:
    if state == "SUPPRESSED":
        return None
    if state in {"ACTIONABLE_NOW", "RESEARCH_REQUIRED"}:
        return evaluated_at if not fired else (
            # if anniversary in future, use event date
            _future_or_now(fired, as_of, evaluated_at)
        )
    # WATCH: schedule reevaluation
    days = int(policy.reevaluation.get("watch_days", 14))
    return (as_of + timedelta(days=days)).isoformat() + "T00:00:00Z"


def _future_or_now(fired: list[Any], as_of: date, evaluated_at: str) -> str:
    for f in fired:
        if f.code == "CONTRACT_ANNIVERSARY_WINDOW" and f.event_date:
            try:
                ed = date.fromisoformat(str(f.event_date)[:10])
                if ed > as_of:
                    return ed.isoformat() + "T00:00:00Z"
            except ValueError:
                pass
    return evaluated_at


def _expires_at(state: str, fired: list[Any], policy: ActivationPolicy, as_of: date) -> str | None:
    if state not in {"ACTIONABLE_NOW", "RESEARCH_REQUIRED"}:
        return None
    dates: list[date] = []
    for f in fired:
        if f.expires_at:
            try:
                dates.append(date.fromisoformat(str(f.expires_at)[:10]))
            except ValueError:
                pass
    if dates:
        return min(dates).isoformat() + "T00:00:00Z"
    ttl = int(policy.reevaluation.get("actionable_ttl_days", 14))
    return (as_of + timedelta(days=ttl)).isoformat() + "T00:00:00Z"


def evaluate_row(
    row: dict[str, Any],
    *,
    policy: ActivationPolicy,
    as_of: date,
    prior: dict[str, Any] | None = None,
    evaluated_at: str | None = None,
) -> ActivationProjection:
    """Evaluate one universe company into an activation projection."""
    cnpj = _digits_cnpj(row)
    if not cnpj:
        raise ValueError("row missing cnpj14")
    evaluated_at = evaluated_at or _utcnow()
    sh = source_hash_for_row(row)
    prior_ctx = dict(prior or {})
    prior_ctx["current_source_hash"] = sh
    if prior and "active_contract_count" not in prior_ctx:
        # allow portfolio deltas from prior projection snapshot fields
        pass

    commercial = _commercial_state(row, prior)
    fired = detect_triggers(row, policy=policy, as_of=as_of, prior=prior_ctx)
    score, components = compute_activation_score(row, fired, policy=policy, as_of=as_of)
    state, codes = _decide_state(
        commercial_state=commercial, fired=fired, policy=policy, score=score
    )

    # Expire stale actionable if expires_at already past
    exp = _expires_at(state, fired, policy, as_of)
    if state == "ACTIONABLE_NOW" and exp:
        try:
            exp_d = date.fromisoformat(exp[:10])
            if exp_d < as_of:
                state = "WATCH"
                codes = codes + ["TRIGGER_EXPIRED"]
        except ValueError:
            pass

    th = stable_hash([f.as_dict() for f in fired])
    nba = _next_best_action(
        state, fired, as_of=as_of, policy=policy, evaluated_at=evaluated_at
    )

    # Preserve durable funnel fields from prior projection
    prior = prior or {}
    ds = str(prior.get("downstream_status") or DOWNSTREAM_PENDING).upper()
    if ds not in {
        "PENDING",
        "SELECTED",
        "INTEL_DONE",
        "CONTACTS_DONE",
        "EXPORTED",
        "FAILED",
        "COOLDOWN",
        "NO_CONTACT",
        "SKIPPED",
    }:
        ds = DOWNSTREAM_PENDING
    next_elig = prior.get("next_eligible_at") or row.get("next_eligible_at")
    last_outcome = prior.get("last_outcome") or row.get("last_outcome")
    port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    value_total = float(port.get("value_total_brl") or 0)
    try:
        pri_score = float(row.get("priority_score") or score)
    except (TypeError, ValueError):
        pri_score = float(score)
    band = priority_band_for(
        activation_state=state,
        activation_score=score if state != "SUPPRESSED" else 0.0,
        commercial_state=commercial,
        downstream_status=ds,
        value_total=value_total,
    )

    proj = ActivationProjection(
        cnpj14=cnpj,
        activation_state=state,
        activation_score=score if state != "SUPPRESSED" else 0.0,
        reason_codes=codes,
        evaluated_at=evaluated_at,
        next_best_action_at=nba,
        expires_at=exp if state in {"ACTIONABLE_NOW", "RESEARCH_REQUIRED"} else None,
        source_hash=sh,
        trigger_hash=th,
        policy_version=policy.policy_version,
        score_components=components.as_dict(),
        fired_triggers=[f.as_dict() for f in fired],
        last_hot_set_at=prior.get("last_hot_set_at"),
        commercial_state=commercial,
        notes=[],
        downstream_status=ds,
        last_downstream_at=prior.get("last_downstream_at"),
        next_eligible_at=str(next_elig) if next_elig else None,
        processing_attempts=int(prior.get("processing_attempts") or 0),
        last_error=prior.get("last_error"),
        last_outcome=str(last_outcome) if last_outcome else None,
        priority_band=band,
        priority_score=pri_score,
    )
    proj.validate()
    return proj


def select_hot_set(
    projections: list[ActivationProjection],
    *,
    policy: ActivationPolicy,
    capacity_override: int | None = None,
    as_of: date | None = None,
    include_watch_fill: bool = True,
    cooldown_days: int = 14,
) -> list[ActivationProjection]:
    """Capacity-aware hot set with durable cursor (no blind re-pick of prior batch).

    Tier 1: ACTIONABLE_NOW / RESEARCH_REQUIRED not yet consumed this cycle.
    Tier 2 (fill): WATCH ordered by score so every eligible remains reachable.

    Score/priority orders work; only objective blocks (DNC, SUPPRESSED, active
    cadence, next_eligible_at in future) exclude. Capacity is operational
    batch size — never the size of the commercial universe.
    """
    budget = capacity_override if capacity_override is not None else policy.capacity.planned_capacity()
    budget = max(0, min(budget, policy.capacity.max_hot_set))
    as_of = as_of or date.today()

    def available(p: ActivationProjection) -> bool:
        if p.activation_state == "SUPPRESSED":
            return False
        if p.commercial_state in policy.suppressed_states:
            return False
        if p.commercial_state in policy.active_commercial_block:
            return False
        prior_snap = {
            "commercial_state": p.commercial_state,
            "last_outcome": p.last_outcome,
            "next_eligible_at": p.next_eligible_at,
            "downstream_status": p.downstream_status,
            "last_downstream_at": p.last_downstream_at,
            "last_hot_set_at": p.last_hot_set_at,
            "source_hash": p.source_hash,
        }
        if not is_reeligible(
            prior_snap,
            as_of=as_of,
            current_source_hash=p.source_hash,
            cooldown_days=cooldown_days,
        ):
            return False
        return True

    tier1 = [
        p
        for p in projections
        if available(p)
        and p.activation_state in {"ACTIONABLE_NOW", "RESEARCH_REQUIRED"}
        and p.activation_score >= policy.hot_set_min_score
    ]
    tier1.sort(
        key=lambda p: (
            0 if p.activation_state == "ACTIONABLE_NOW" else 1,
            -p.activation_score,
            p.cnpj14,
        )
    )
    selected: list[ActivationProjection] = []
    seen: set[str] = set()
    for p in tier1:
        if len(selected) >= budget:
            break
        selected.append(p)
        seen.add(p.cnpj14)

    if include_watch_fill and len(selected) < budget:
        tier2 = [
            p
            for p in projections
            if available(p)
            and p.cnpj14 not in seen
            and p.activation_state == "WATCH"
        ]
        # Prefer higher activation_score then priority_score then stable cnpj
        tier2.sort(key=lambda p: (-p.activation_score, -p.priority_score, p.cnpj14))
        for p in tier2:
            if len(selected) >= budget:
                break
            selected.append(p)
            seen.add(p.cnpj14)

    return selected


def compute_deltas(
    previous: dict[str, dict[str, Any]],
    current: list[ActivationProjection],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (deactivations, promotions, rows_changed)."""
    deacts: list[dict[str, Any]] = []
    promos: list[dict[str, Any]] = []
    changed = 0
    cur_by = {p.cnpj14: p for p in current}
    for cnpj, prev in previous.items():
        prev_state = str(prev.get("activation_state") or "")
        cur = cur_by.get(cnpj)
        if cur is None:
            continue
        if prev_state != cur.activation_state or prev.get("source_hash") != cur.source_hash:
            changed += 1
        if prev_state == "ACTIONABLE_NOW" and cur.activation_state in {
            "WATCH",
            "SUPPRESSED",
            "RESEARCH_REQUIRED",
        }:
            deacts.append(
                {
                    "cnpj14": cnpj,
                    "from_state": prev_state,
                    "to_state": cur.activation_state,
                    "reason_codes": list(cur.reason_codes),
                    "evaluated_at": cur.evaluated_at,
                    "source_hash": cur.source_hash,
                    "policy_version": cur.policy_version,
                }
            )
        if prev_state in {"WATCH", "RESEARCH_REQUIRED", ""} and cur.activation_state == "ACTIONABLE_NOW":
            promos.append(
                {
                    "cnpj14": cnpj,
                    "from_state": prev_state or "WATCH",
                    "to_state": cur.activation_state,
                    "reason_codes": list(cur.reason_codes),
                    "activation_score": cur.activation_score,
                    "evaluated_at": cur.evaluated_at,
                }
            )
    # New ACTIONABLE without prior
    for p in current:
        if p.cnpj14 not in previous and p.activation_state == "ACTIONABLE_NOW":
            promos.append(
                {
                    "cnpj14": p.cnpj14,
                    "from_state": "NONE",
                    "to_state": p.activation_state,
                    "reason_codes": list(p.reason_codes),
                    "activation_score": p.activation_score,
                    "evaluated_at": p.evaluated_at,
                }
            )
            changed += 1
    return deacts, promos, changed


def run_activation_cycle(
    universe_rows: list[dict[str, Any]],
    *,
    policy: ActivationPolicy | None = None,
    policy_path: str | None = None,
    as_of: date | None = None,
    prior_projections: dict[str, dict[str, Any]] | None = None,
    capacity_override: int | None = None,
    evaluated_at: str | None = None,
    commercial_memory: dict[str, dict[str, Any]] | None = None,
    include_watch_fill: bool = True,
) -> ActivationCycleResult:
    """Process full reservoir cheaply; return projections + hot set + deltas.

    Does NOT run LLM or account intelligence. Bounded memory: one pass.
    capacity_override bounds this round's expensive batch only — never the
    universe size. Prior projections + commercial_memory advance the cursor.
    """
    started = time.monotonic()
    pol = policy or load_policy(policy_path)
    as_of = as_of or date.today()
    evaluated_at = evaluated_at or _utcnow()
    prior = prior_projections or {}
    memory = commercial_memory or {}

    projections: list[ActivationProjection] = []
    counts = {
        "WATCH": 0,
        "RESEARCH_REQUIRED": 0,
        "ACTIONABLE_NOW": 0,
        "SUPPRESSED": 0,
    }

    for raw_row in universe_rows:
        row = apply_commercial_memory(raw_row, memory)
        cnpj = _digits_cnpj(row)
        if not cnpj:
            continue
        # Skip non-eligible for commercial activation (still reservoir membership
        # is caller's responsibility — we only plan eligible construction B2G).
        elig = str(row.get("outreach_eligibility") or "ELIGIBLE").upper()
        if elig not in {"ELIGIBLE", "DNC", "DO_NOT_CONTACT", ""}:
            # Keep non-construction out of activation counts but still WATCH if passed
            pass
        prev = prior.get(cnpj)
        # Merge memory into prior for durable commercial_state
        prior_for_row: dict[str, Any] = dict(prev or {})
        if cnpj in memory:
            mem = memory[cnpj]
            if mem.get("commercial_state"):
                prior_for_row["commercial_state"] = mem["commercial_state"]
            if mem.get("next_eligible_at"):
                prior_for_row["next_eligible_at"] = mem["next_eligible_at"]
            if mem.get("last_outcome"):
                prior_for_row["last_outcome"] = mem["last_outcome"]
            if mem.get("downstream_status"):
                prior_for_row["downstream_status"] = mem["downstream_status"]
        proj = evaluate_row(
            row,
            policy=pol,
            as_of=as_of,
            prior=prior_for_row,
            evaluated_at=evaluated_at,
        )
        projections.append(proj)
        counts[proj.activation_state] = counts.get(proj.activation_state, 0) + 1

    # Count trigger codes from fired_triggers for accuracy
    trigger_counts: dict[str, int] = {}
    for p in projections:
        for ft in p.fired_triggers:
            code = str(ft.get("code") or "")
            if code:
                trigger_counts[code] = trigger_counts.get(code, 0) + 1

    hot = select_hot_set(
        projections,
        policy=pol,
        capacity_override=capacity_override,
        as_of=as_of,
        include_watch_fill=include_watch_fill,
    )
    hot_at = evaluated_at
    for p in hot:
        p.last_hot_set_at = hot_at
        p.downstream_status = DOWNSTREAM_SELECTED
        p.last_downstream_at = hot_at
        p.processing_attempts = int(p.processing_attempts or 0) + 1

    deacts, promos, rows_changed = compute_deltas(prior, projections)

    # Watermark from max last_contract_date
    watermark_parts: list[str] = []
    for row in universe_rows[:5000]:  # bounded sample for watermark string stability
        port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
        lcd = port.get("last_contract_date")
        if lcd:
            watermark_parts.append(str(lcd))
    source_watermark = stable_hash(
        {
            "as_of": as_of.isoformat(),
            "reservoir": len(projections),
            "policy": pol.policy_version,
            "max_last": max(watermark_parts) if watermark_parts else "",
        }
    )

    return ActivationCycleResult(
        policy_version=pol.policy_version,
        evaluated_at=evaluated_at,
        as_of=as_of.isoformat(),
        reservoir_count=len(projections),
        activation_counts=counts,
        hot_set_count=len(hot),
        projections=projections,
        hot_set=hot,
        deactivations=deacts,
        promotions=promos,
        source_watermark=source_watermark,
        trigger_counts=dict(sorted(trigger_counts.items())),
        rows_changed=rows_changed,
        elapsed_seconds=round(time.monotonic() - started, 3),
        peak_rss_mb=_peak_rss_mb(),
    )
