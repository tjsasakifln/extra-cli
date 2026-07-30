#!/usr/bin/env python3
"""Strict actionable-opportunity classification for Extra decision loop.

A tender is ACTIONABLE only with verifiable future deadline, known timezone,
compatible status, traceable source, profile compatibility, and no critical
profile block. Synthetic openness is forbidden.

States:
  ACTIONABLE
  EXPIRED
  NO_VERIFIABLE_FUTURE_DEADLINE
  STATUS_UNCONFIRMED
  PROFILE_BLOCKED
  INSUFFICIENT_SOURCE_EVIDENCE
  DUPLICATE
  REVIEW_REQUIRED
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from scripts.ops.extra_first_client_delivery import (
    build_pncp_specific_url,
    is_terminal_status,
    match_terms,
    parse_date,
    parse_float,
)
from scripts.ops.extra_profile import critical_pending, load_raw, stamp

SCHEMA = "extra-actionable-opportunity/1.0"
DEFAULT_TZ = "America/Sao_Paulo"

ACTIONABLE = "ACTIONABLE"
EXPIRED = "EXPIRED"
NO_VERIFIABLE_FUTURE_DEADLINE = "NO_VERIFIABLE_FUTURE_DEADLINE"
STATUS_UNCONFIRMED = "STATUS_UNCONFIRMED"
PROFILE_BLOCKED = "PROFILE_BLOCKED"
INSUFFICIENT_SOURCE_EVIDENCE = "INSUFFICIENT_SOURCE_EVIDENCE"
DUPLICATE = "DUPLICATE"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

OPENISH_STATUS = frozenset(
    {
        "open",
        "aberto",
        "aberta",
        "recebendo proposta",
        "em andamento",
        "upcoming",
        "agendada",
        "divulgada",
    }
)


@dataclass
class ActionableResult:
    opportunity_id: str | None
    state: str
    actionable: bool
    reasons_include: list[str] = field(default_factory=list)
    reasons_block: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    score_components: dict[str, Any] = field(default_factory=dict)
    profile_stamp: dict[str, Any] = field(default_factory=dict)
    parser_version: str = SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_deadline_aware(
    value: Any, *, timezone_name: str = DEFAULT_TZ
) -> tuple[datetime | None, str | None, list[str]]:
    """Return (deadline_dt_utc, tz_used, issues)."""
    issues: list[str] = []
    if value in (None, ""):
        return None, None, ["deadline_missing"]

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            try:
                tz = ZoneInfo(timezone_name)
            except Exception:
                tz = ZoneInfo(DEFAULT_TZ)
                issues.append("timezone_fallback_default")
            dt = dt.replace(tzinfo=tz)
            return dt.astimezone(UTC), timezone_name, issues
        return dt.astimezone(UTC), str(dt.tzinfo), issues

    text = str(value).strip()
    # ISO with offset
    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.astimezone(UTC), "UTC", issues
        if "T" in text and ("+" in text[10:] or text.count("-") > 2):
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                issues.append("deadline_naive_datetime")
                tz = ZoneInfo(timezone_name)
                dt = dt.replace(tzinfo=tz)
            return dt.astimezone(UTC), timezone_name, issues
    except ValueError:
        pass

    d = parse_date(text)
    if d is None:
        return None, None, ["deadline_unparseable"]
    # Date-only: end of day in Brazil business TZ (explicit, not silent UTC midnight)
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
        issues.append("timezone_fallback_default")
    dt_local = datetime.combine(d, time(23, 59, 59), tzinfo=tz)
    issues.append("deadline_date_only_eod_assumed")
    return dt_local.astimezone(UTC), timezone_name, issues


def classify_opportunity(
    row: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    profile_path: str | None = None,
    as_of: datetime | None = None,
    seen_ids: set[str] | None = None,
    timezone_name: str = DEFAULT_TZ,
) -> ActionableResult:
    raw_profile = profile if profile is not None else load_raw(profile_path)
    st = stamp(profile_path) if profile_path else {
        "profile_id": raw_profile.get("profile_id"),
        "version": raw_profile.get("version"),
        "profile_hash": hashlib.sha256(
            json.dumps(raw_profile, sort_keys=True, default=str).encode()
        ).hexdigest(),
        "stamp": f"{raw_profile.get('profile_id')}@v{raw_profile.get('version')}",
    }
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    oid = str(
        row.get("numero_controle_pncp")
        or row.get("source_id")
        or row.get("opportunity_id")
        or row.get("id")
        or ""
    ).strip() or None

    reasons_block: list[str] = []
    reasons_include: list[str] = []
    score: dict[str, Any] = {}

    # Duplicate
    if oid and seen_ids is not None and oid in seen_ids:
        return ActionableResult(
            opportunity_id=oid,
            state=DUPLICATE,
            actionable=False,
            reasons_block=["duplicate_id"],
            evidence={"opportunity_id": oid},
            profile_stamp=st,
        )
    if oid and seen_ids is not None:
        seen_ids.add(oid)

    # Deadline
    deadline_raw = (
        row.get("data_encerramento")
        or row.get("data_limite")
        or row.get("deadline")
        or row.get("closing_at")
    )
    deadline_dt, tz_used, dl_issues = _parse_deadline_aware(
        deadline_raw, timezone_name=str(row.get("timezone") or timezone_name)
    )
    reasons_block.extend(dl_issues)

    # Status
    status = str(row.get("status_canonico") or row.get("status") or "").strip().lower()
    if not status:
        reasons_block.append("status_missing")
    elif is_terminal_status(status):
        reasons_block.append(f"terminal_status:{status}")
    elif status not in OPENISH_STATUS and status not in {"unknown", "desconhecido"}:
        # Unknown non-terminal → unconfirmed rather than auto-open
        reasons_block.append(f"status_not_confirmed_open:{status}")
    else:
        reasons_include.append(f"status_compatible:{status or 'openish'}")

    # Source evidence
    source = row.get("source") or row.get("fonte") or row.get("origem")
    source_url = row.get("link_edital") or row.get("source_url") or row.get("url")
    url, url_specific = build_pncp_specific_url(
        row.get("numero_controle_pncp") or row.get("source_id"),
        source_url,
    )
    collected_at = row.get("ingested_at") or row.get("collected_at") or row.get("updated_at")
    source_updated = row.get("source_updated_at") or row.get("data_atualizacao") or collected_at
    if not source:
        reasons_block.append("source_missing")
    if not oid:
        reasons_block.append("identity_missing")
    if not url_specific:
        reasons_block.append("url_not_specific")
    if not source_updated:
        reasons_block.append("source_update_timestamp_missing")

    # Profile compatibility
    pending = critical_pending(raw_profile)
    hard = raw_profile.get("hard_blocks") if isinstance(raw_profile.get("hard_blocks"), dict) else {}
    objeto = str(row.get("objeto") or "")
    pos_terms = list(raw_profile.get("positive_terms") or [])
    for ot in raw_profile.get("desired_object_types") or []:
        if isinstance(ot, dict):
            pos_terms.extend(ot.get("terms") or [])
    neg_terms = list(raw_profile.get("negative_terms") or [])
    pos_hits = match_terms(objeto, pos_terms)
    neg_hits = match_terms(objeto, neg_terms)

    if hard.get("require_future_deadline", True) and deadline_dt is None:
        reasons_block.append("profile_requires_future_deadline")
    if hard.get("exclude_terminal_or_suspended", True) and is_terminal_status(status):
        reasons_block.append("profile_excludes_terminal")
    if hard.get("require_official_url", True) and not url_specific:
        reasons_block.append("profile_requires_official_url")

    if neg_hits and not pos_hits:
        reasons_block.append("profile_negative_object")
    if not pos_hits:
        reasons_block.append("profile_no_positive_terms")

    # Value band soft only (absence of max is not infinite capacity)
    valor = parse_float(row.get("valor_estimado") or row.get("valor"))
    band = raw_profile.get("value_band_soft") if isinstance(raw_profile.get("value_band_soft"), dict) else {}
    vmax = parse_float(raw_profile.get("maximum_value") or band.get("max_brl"))
    vmin = parse_float(raw_profile.get("minimum_value") or band.get("min_brl"))
    if valor is not None and vmax is not None and valor > vmax:
        reasons_block.append("above_max_value")
    if valor is not None and vmin is not None and valor < vmin:
        reasons_block.append("below_min_value")

    # Temporal classification
    if deadline_dt is None:
        temporal_state = NO_VERIFIABLE_FUTURE_DEADLINE
    elif deadline_dt < now:
        temporal_state = EXPIRED
        reasons_block.append("deadline_in_past")
    else:
        temporal_state = ACTIONABLE
        reasons_include.append("future_deadline_verified")
        score["days_remaining"] = (deadline_dt - now).total_seconds() / 86400.0

    # Aggregate state priority
    if temporal_state == EXPIRED:
        state = EXPIRED
    elif temporal_state == NO_VERIFIABLE_FUTURE_DEADLINE:
        state = NO_VERIFIABLE_FUTURE_DEADLINE
    elif any(x.startswith("status_") or x.startswith("terminal_") for x in reasons_block) and (
        "status_missing" in reasons_block or "status_not_confirmed_open" in reasons_block
    ):
        state = STATUS_UNCONFIRMED
    elif any(
        x.startswith("source_") or x in {"url_not_specific", "identity_missing", "source_update_timestamp_missing"}
        for x in reasons_block
    ):
        state = INSUFFICIENT_SOURCE_EVIDENCE
    elif any(x.startswith("profile_") for x in reasons_block) or "above_max_value" in reasons_block:
        state = PROFILE_BLOCKED
    elif pending and hard.get("block_actionable_while_capacity_pending"):
        state = PROFILE_BLOCKED
        reasons_block.append("critical_capacity_pending:" + ",".join(pending))
    elif reasons_block:
        # residual issues → human review, not false ACTIONABLE
        state = REVIEW_REQUIRED
    else:
        state = ACTIONABLE
        reasons_include.append("all_actionable_gates_passed")

    # Critical capacity pending never mint silent GO-grade actionable commercial certainty
    if state == ACTIONABLE and pending:
        state = REVIEW_REQUIRED
        reasons_block.append("capacity_pending_forces_review:" + ",".join(pending))
        reasons_include = [r for r in reasons_include if r != "all_actionable_gates_passed"]
        reasons_include.append("actionable_candidate_pending_capacity_review")

    actionable = state == ACTIONABLE
    score["positive_term_hits"] = len(pos_hits)
    score["negative_term_hits"] = len(neg_hits)
    score["valor"] = valor

    evidence = {
        "opportunity_id": oid,
        "orgao": row.get("orgao_nome") or row.get("orgao"),
        "objeto": objeto[:500] if objeto else None,
        "modalidade": row.get("modalidade"),
        "valor": valor,
        "valor_semantica": row.get("valor_semantica"),
        "publicacao": row.get("data_publicacao") or row.get("published_at"),
        "prazo_raw": deadline_raw,
        "prazo_utc": deadline_dt.isoformat().replace("+00:00", "Z") if deadline_dt else None,
        "timezone": tz_used,
        "status": status or None,
        "source": source,
        "url": url,
        "url_specific": url_specific,
        "collected_at": collected_at,
        "source_updated_at": source_updated,
        "parser_version": SCHEMA,
        "profile_stamp": st,
        "positive_terms": pos_hits,
        "negative_terms": neg_hits,
        "critical_capacity_pending": pending,
    }

    return ActionableResult(
        opportunity_id=oid,
        state=state,
        actionable=actionable,
        reasons_include=reasons_include,
        reasons_block=reasons_block,
        evidence=evidence,
        score_components=score,
        profile_stamp=st,
    )


def classify_batch(
    rows: list[dict[str, Any]],
    *,
    profile_path: str | None = None,
    profile: dict[str, Any] | None = None,
    as_of: datetime | None = None,
    max_shortlist: int = 5,
) -> dict[str, Any]:
    raw = profile if profile is not None else load_raw(profile_path)
    st = stamp(profile_path) if profile_path else stamp()
    seen: set[str] = set()
    results = [
        classify_opportunity(
            r,
            profile=raw,
            profile_path=profile_path,
            as_of=as_of,
            seen_ids=seen,
        )
        for r in rows
    ]
    by_state: dict[str, int] = {}
    for r in results:
        by_state[r.state] = by_state.get(r.state, 0) + 1

    actionable = [r for r in results if r.actionable]

    def sort_key(r: ActionableResult) -> tuple:
        days = r.score_components.get("days_remaining")
        days_n = float(days) if days is not None else 9999.0
        pos = -int(r.score_components.get("positive_term_hits") or 0)
        return (days_n, pos)

    shortlist = sorted(actionable, key=sort_key)[:max_shortlist]
    no_actionable = len(shortlist) == 0
    pending = critical_pending(raw)

    summary = {
        "schema": SCHEMA,
        "as_of": (as_of or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        "profile_stamp": st,
        "candidates_evaluated": len(results),
        "by_state": by_state,
        "expired": by_state.get(EXPIRED, 0),
        "no_verifiable_future_deadline": by_state.get(NO_VERIFIABLE_FUTURE_DEADLINE, 0),
        "profile_blocked": by_state.get(PROFILE_BLOCKED, 0),
        "insufficient_source": by_state.get(INSUFFICIENT_SOURCE_EVIDENCE, 0),
        "review_required": by_state.get(REVIEW_REQUIRED, 0),
        "actionable_count": len(actionable),
        "shortlist": [r.as_dict() for r in shortlist],
        "shortlist_count": len(shortlist),
        "result": "NO_ACTIONABLE_TENDER" if no_actionable else "SHORTLIST_READY",
        "critical_profile_pending": pending,
        "coverage_actions": _coverage_actions(by_state, pending),
        "all_results": [r.as_dict() for r in results],
    }
    return summary


def _coverage_actions(by_state: dict[str, int], pending: list[str]) -> list[str]:
    actions: list[str] = []
    if by_state.get(NO_VERIFIABLE_FUTURE_DEADLINE, 0):
        actions.append("Melhorar normalização de prazos e timezone na fonte PNCP.")
    if by_state.get(INSUFFICIENT_SOURCE_EVIDENCE, 0):
        actions.append("Garantir URL específica e timestamp de atualização da fonte.")
    if by_state.get(PROFILE_BLOCKED, 0) or pending:
        actions.append(
            "Completar intake do perfil Extra: " + (", ".join(pending) if pending else "revisar exclusões")
        )
    if by_state.get(EXPIRED, 0) and not by_state.get(ACTIONABLE, 0):
        actions.append("Ampliar lookback/coleta de editais vigentes; não reutilizar históricos como abertos.")
    if not actions:
        actions.append("Manter ciclo weekly e revisão humana da shortlist.")
    return actions
