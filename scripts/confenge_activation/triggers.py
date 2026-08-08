"""Deterministic commercial triggers from universe rows (observational only).

Never invents legal facts from dates alone.
Never claims unpaid reajuste from anniversary windows.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from scripts.confenge_activation.models import FiredTrigger
from scripts.confenge_activation.policy import ActivationPolicy, TriggerDef


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _portfolio(row: dict[str, Any]) -> dict[str, Any]:
    p = row.get("portfolio")
    return p if isinstance(p, dict) else {}


def _recent_contracts(row: dict[str, Any]) -> list[dict[str, Any]]:
    p = _portfolio(row)
    rc = p.get("recent_contracts") or row.get("recent_contracts") or []
    return [c for c in rc if isinstance(c, dict)] if isinstance(rc, list) else []


def _object_blob(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for c in _recent_contracts(row):
        for k in ("objeto", "object", "category", "descricao"):
            if c.get(k):
                parts.append(str(c[k]))
    ce = row.get("construction_evidence")
    if isinstance(ce, dict):
        for k in ("object_snippets", "categories", "notes"):
            v = ce.get(k)
            if isinstance(v, list):
                parts.extend(str(x) for x in v)
            elif v:
                parts.append(str(v))
    return " ".join(parts).lower()


def _sector_fit(row: dict[str, Any]) -> str:
    ce = row.get("construction_evidence")
    if isinstance(ce, dict):
        return str(ce.get("sector_fit") or ce.get("fit") or "").upper()
    return ""


def _expires_at(tdef: TriggerDef, as_of: date, event: date | None) -> str | None:
    if tdef.expires_days is None:
        return None
    base = event or as_of
    return (base + timedelta(days=int(tdef.expires_days))).isoformat()


def _fire(
    tdef: TriggerDef,
    *,
    as_of: date,
    event: date | None,
    details: dict[str, Any] | None = None,
) -> FiredTrigger:
    return FiredTrigger(
        code=tdef.code,
        strength=float(tdef.strength),
        event_date=event.isoformat() if event else as_of.isoformat(),
        language=tdef.language,
        promotes_to=tdef.promotes_to,
        expires_at=_expires_at(tdef, as_of, event),
        details=details or {},
    )


def detect_triggers(
    row: dict[str, Any],
    *,
    policy: ActivationPolicy,
    as_of: date,
    prior: dict[str, Any] | None = None,
) -> list[FiredTrigger]:
    """Evaluate enabled triggers for one universe row. Pure / deterministic."""
    fired: list[FiredTrigger] = []
    prior = prior or {}
    port = _portfolio(row)
    last_dt = _parse_date(port.get("last_contract_date") or row.get("last_contract_date"))
    first_dt = _parse_date(port.get("first_contract_date") or row.get("first_contract_date"))
    active_count = _safe_int(port.get("active_contract_count"))
    recent_count = _safe_int(port.get("contract_count_recent"))
    fit = _sector_fit(row)
    relevant_ok = fit in {
        "CONFIRMED_ENGINEERING",
        "STRONG_ENGINEERING_FIT",
        "POSSIBLE_ENGINEERING_FIT",
    } or _safe_int(
        (row.get("construction_evidence") or {}).get("relevant_contract_count")
        if isinstance(row.get("construction_evidence"), dict)
        else 0
    ) > 0
    blob = _object_blob(row)
    priority = _safe_float(row.get("priority_score"))

    # NEW_RELEVANT_CONTRACT
    t = policy.trigger("NEW_RELEVANT_CONTRACT")
    if t and t.enabled and last_dt and relevant_ok:
        recency = int(t.raw.get("recency_days", 45))
        days = (as_of - last_dt).days
        if 0 <= days <= recency:
            # Do not promote solely because value is large — recency + relevance only.
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={"days_since_last": days, "observational": True},
                )
            )

    # MATERIAL_PORTFOLIO_CHANGE (vs prior projection portfolio counters only)
    t = policy.trigger("MATERIAL_PORTFOLIO_CHANGE")
    if t and t.enabled and prior and (
        "active_contract_count" in prior or "contract_count_recent" in prior
    ):
        prev_active = _safe_int(prior.get("active_contract_count"))
        prev_recent = _safe_int(prior.get("contract_count_recent"))
        min_a = int(t.raw.get("min_active_delta", 2))
        min_r = int(t.raw.get("min_recent_delta", 3))
        da = active_count - prev_active
        dr = recent_count - prev_recent
        if abs(da) >= min_a or abs(dr) >= min_r:
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={
                        "active_delta": da,
                        "recent_delta": dr,
                        "observational": True,
                    },
                )
            )

    # CONTRACT_ANNIVERSARY_WINDOW — temporal window only, not "reajuste devido"
    t = policy.trigger("CONTRACT_ANNIVERSARY_WINDOW")
    if t and t.enabled and first_dt:
        window = int(t.raw.get("anniversary_window_days", 30))
        min_age = int(t.raw.get("min_contract_age_days", 300))
        age = (as_of - first_dt).days
        if age >= min_age:
            # Distance to nearest anniversary of first_contract_date
            years = max(1, as_of.year - first_dt.year)
            candidates = []
            for y in (years - 1, years, years + 1):
                try:
                    ann = date(first_dt.year + y, first_dt.month, first_dt.day)
                except ValueError:
                    # Feb 29
                    ann = date(first_dt.year + y, first_dt.month, 28)
                candidates.append(ann)
            nearest = min(candidates, key=lambda d: abs((d - as_of).days))
            dist = (nearest - as_of).days
            if abs(dist) <= window:
                fired.append(
                    _fire(
                        t,
                        as_of=as_of,
                        event=nearest,
                        details={
                            "anniversary_date": nearest.isoformat(),
                            "days_to_anniversary": dist,
                            "note": (
                                "Janela temporal que justifica verificar formalização; "
                                "não afirma reajuste devido ou não pago."
                            ),
                        },
                    )
                )

    # NEW_AMENDMENT_OR_TERM — keyword on public objects only
    t = policy.trigger("NEW_AMENDMENT_OR_TERM")
    if t and t.enabled:
        kws = [str(k).lower() for k in (t.raw.get("object_keywords") or [])]
        if kws and any(k in blob for k in kws):
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={"matched_keywords": [k for k in kws if k in blob]},
                )
            )

    # CONTRACT_ENDING_WINDOW — only when data_fim exists
    t = policy.trigger("CONTRACT_ENDING_WINDOW")
    if t and t.enabled:
        within = int(t.raw.get("ending_within_days", 90))
        best_end: date | None = None
        for c in _recent_contracts(row):
            end = _parse_date(c.get("data_fim") or c.get("end_date"))
            if end is None:
                continue
            days_left = (end - as_of).days
            if 0 <= days_left <= within:
                if best_end is None or end < best_end:
                    best_end = end
        if best_end is not None:
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=best_end,
                    details={
                        "data_fim": best_end.isoformat(),
                        "days_to_end": (best_end - as_of).days,
                        "note": "Observational vigência; not automatic renewal claim.",
                    },
                )
            )

    # CONTRACT_EXTENSION_OR_PROROGATION
    t = policy.trigger("CONTRACT_EXTENSION_OR_PROROGATION")
    if t and t.enabled:
        kws = [str(k).lower() for k in (t.raw.get("object_keywords") or [])]
        if kws and any(k in blob for k in kws):
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={"matched_keywords": [k for k in kws if k in blob]},
                )
            )

    # NEW_RELEVANT_PROCUREMENT
    t = policy.trigger("NEW_RELEVANT_PROCUREMENT")
    if t and t.enabled:
        kws = [str(k).lower() for k in (t.raw.get("object_keywords") or [])]
        if kws and any(k in blob for k in kws) and last_dt and (as_of - last_dt).days <= 90:
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={"matched_keywords": [k for k in kws if k in blob]},
                )
            )

    # MATERIAL_CONTRACT_CHANGE via prior source_hash divergence
    t = policy.trigger("MATERIAL_CONTRACT_CHANGE")
    if t and t.enabled and prior.get("source_hash"):
        # Caller supplies current source_hash in prior["current_source_hash"] after compute
        cur = prior.get("current_source_hash")
        if cur and cur != prior.get("source_hash") and (active_count > 0 or recent_count > 0):
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={"prior_source_hash": prior.get("source_hash"), "observational": True},
                )
            )

    # RESEARCH_GAP_WORTH_RESOLVING
    t = policy.trigger("RESEARCH_GAP_WORTH_RESOLVING")
    if t and t.enabled and last_dt:
        min_pri = float(t.raw.get("min_priority_score", 50))
        max_days = int(t.raw.get("max_days_since_last_contract", 120))
        days = (as_of - last_dt).days
        has_thin_intel = not row.get("_has_deep_intel")
        if priority >= min_pri and 0 <= days <= max_days and has_thin_intel and relevant_ok:
            fired.append(
                _fire(
                    t,
                    as_of=as_of,
                    event=last_dt,
                    details={"priority_score": priority, "days_since_last": days},
                )
            )

    # NEW_RELEVANT_PROCESS_DOCUMENT — only with explicit signal flag (no invention)
    t = policy.trigger("NEW_RELEVANT_PROCESS_DOCUMENT")
    if t and t.enabled and row.get("new_process_document") is True:
        fired.append(
            _fire(
                t,
                as_of=as_of,
                event=_parse_date(row.get("new_process_document_date")) or as_of,
                details={"explicit_signal": True},
            )
        )

    # Stable order by strength desc then code
    fired.sort(key=lambda f: (-f.strength, f.code))
    return fired
