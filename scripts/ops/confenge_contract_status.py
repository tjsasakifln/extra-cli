#!/usr/bin/env python3
"""Explicit contract lifecycle status normalization for CONFENGE snapshots.

Never sets is_active=TRUE for all rows. Never invents CANCELLED/TERMINATED
without a stored rule. Date-based completion is allowed only when the rule id
is persisted in status_reason / status_source.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

NORMALIZED_STATUSES = (
    "ACTIVE",
    "COMPLETED",
    "CANCELLED",
    "TERMINATED",
    "SUSPENDED",
    "UNKNOWN",
)

# Rule ids — never invent closure without recording one of these.
RULE_SOURCE_STATUS_ACTIVE = "source_status_active_v1"
RULE_SOURCE_STATUS_COMPLETED = "source_status_completed_v1"
RULE_SOURCE_STATUS_CANCELLED = "source_status_cancelled_v1"
RULE_SOURCE_STATUS_TERMINATED = "source_status_terminated_v1"
RULE_SOURCE_STATUS_SUSPENDED = "source_status_suspended_v1"
RULE_DATA_FIM_BEFORE_AS_OF = "data_fim_before_as_of_v1"
RULE_DATA_FIM_NULL_OR_FUTURE = "data_fim_null_or_future_v1"
RULE_NO_STATUS_SIGNAL = "no_status_signal_unknown_v1"

# Text tokens observed in PNCP / portal feeds (when present).
_ACTIVE_TOKENS = frozenset(
    {
        "ativo",
        "ativa",
        "vigente",
        "em execucao",
        "em execução",
        "em andamento",
        "active",
        "1",
        "true",
        "t",
    }
)
_COMPLETED_TOKENS = frozenset(
    {
        "concluido",
        "concluído",
        "encerrado",
        "encerrada",
        "finalizado",
        "finalizada",
        "extinto",
        "extinta",
        "cumprido",
        "completed",
        "finished",
    }
)
_CANCELLED_TOKENS = frozenset(
    {
        "cancelado",
        "cancelada",
        "anulado",
        "anulada",
        "revogado",
        "revogada",
        "cancelled",
        "canceled",
    }
)
_TERMINATED_TOKENS = frozenset(
    {
        "rescindido",
        "rescindida",
        "resilido",
        "resilida",
        "terminated",
        "distrato",
    }
)
_SUSPENDED_TOKENS = frozenset(
    {
        "suspenso",
        "suspensa",
        "paralisado",
        "paralisada",
        "suspended",
    }
)


def _norm_token(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    # collapse accents lightly for matching
    repl = (
        ("á", "a"),
        ("à", "a"),
        ("â", "a"),
        ("ã", "a"),
        ("é", "e"),
        ("ê", "e"),
        ("í", "i"),
        ("ó", "o"),
        ("ô", "o"),
        ("õ", "o"),
        ("ú", "u"),
        ("ç", "c"),
    )
    for a, b in repl:
        s = s.replace(a, b)
    return " ".join(s.split())


def _parse_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _map_source_status_token(token: str) -> tuple[str, str] | None:
    if not token:
        return None
    # exact token match first
    if token in _ACTIVE_TOKENS:
        return "ACTIVE", RULE_SOURCE_STATUS_ACTIVE
    if token in _COMPLETED_TOKENS:
        return "COMPLETED", RULE_SOURCE_STATUS_COMPLETED
    if token in _CANCELLED_TOKENS:
        return "CANCELLED", RULE_SOURCE_STATUS_CANCELLED
    if token in _TERMINATED_TOKENS:
        return "TERMINATED", RULE_SOURCE_STATUS_TERMINATED
    if token in _SUSPENDED_TOKENS:
        return "SUSPENDED", RULE_SOURCE_STATUS_SUSPENDED
    # substring containment for free-text situacao
    for tok, status, rule in (
        (_CANCELLED_TOKENS, "CANCELLED", RULE_SOURCE_STATUS_CANCELLED),
        (_TERMINATED_TOKENS, "TERMINATED", RULE_SOURCE_STATUS_TERMINATED),
        (_SUSPENDED_TOKENS, "SUSPENDED", RULE_SOURCE_STATUS_SUSPENDED),
        (_COMPLETED_TOKENS, "COMPLETED", RULE_SOURCE_STATUS_COMPLETED),
        (_ACTIVE_TOKENS, "ACTIVE", RULE_SOURCE_STATUS_ACTIVE),
    ):
        if any(t in token for t in tok if len(t) >= 4):
            return status, rule
    return None


def normalize_contract_status(
    row: dict[str, Any],
    *,
    as_of: date | None = None,
    allow_data_fim_inference: bool = True,
) -> dict[str, Any]:
    """Return status fields for one contract row.

    Priority:
      1. Explicit source status / situacao fields from the feed
      2. Boolean is_active only when source already provided it with a reason
      3. data_fim vs as_of (explicit rule data_fim_before_as_of_v1) when enabled
      4. UNKNOWN — never invent CANCELLED/TERMINATED without a rule
    """
    as_of = as_of or date.today()
    source_status = (
        row.get("source_status")
        or row.get("situacao")
        or row.get("situacao_contrato")
        or row.get("status")
        or row.get("contrato_situacao")
    )
    token = _norm_token(source_status)
    observed_at = datetime.now(UTC).replace(microsecond=0).isoformat() + "Z"

    mapped = _map_source_status_token(token) if token else None
    if mapped:
        normalized, rule = mapped
        is_active = normalized == "ACTIVE"
        return {
            "source_status": str(source_status) if source_status is not None else None,
            "normalized_status": normalized,
            "is_active": is_active,
            "status_reason": rule,
            "status_source": "source_feed_field",
            "status_observed_at": observed_at,
        }

    # Preserve explicit boolean is_active from a prior authentic export only when
    # no text status exists and inference is not inventing closed classes.
    if "is_active" in row and row.get("is_active") is not None and not allow_data_fim_inference:
        active = bool(row["is_active"])
        return {
            "source_status": str(source_status) if source_status is not None else None,
            "normalized_status": "ACTIVE" if active else "UNKNOWN",
            "is_active": active,
            "status_reason": "explicit_is_active_flag_v1",
            "status_source": "source_is_active_column",
            "status_observed_at": observed_at,
        }

    if allow_data_fim_inference:
        fim = _parse_date(row.get("data_fim"))
        if fim is not None and fim < as_of:
            return {
                "source_status": str(source_status) if source_status is not None else None,
                "normalized_status": "COMPLETED",
                "is_active": False,
                "status_reason": RULE_DATA_FIM_BEFORE_AS_OF,
                "status_source": "derived_from_data_fim",
                "status_observed_at": observed_at,
                "data_fim": fim.isoformat(),
                "as_of": as_of.isoformat(),
            }
        if fim is None or fim >= as_of:
            return {
                "source_status": str(source_status) if source_status is not None else None,
                "normalized_status": "ACTIVE",
                "is_active": True,
                "status_reason": RULE_DATA_FIM_NULL_OR_FUTURE,
                "status_source": "derived_from_data_fim",
                "status_observed_at": observed_at,
                "data_fim": fim.isoformat() if fim else None,
                "as_of": as_of.isoformat(),
            }

    return {
        "source_status": str(source_status) if source_status is not None else None,
        "normalized_status": "UNKNOWN",
        "is_active": False,
        "status_reason": RULE_NO_STATUS_SIGNAL,
        "status_source": "none",
        "status_observed_at": observed_at,
    }


def reconcile_status_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum invariant: active+completed+cancelled+terminated+suspended+unknown == total."""
    counts = {s.lower(): 0 for s in NORMALIZED_STATUSES}
    counts["total"] = 0
    for r in rows:
        st = str(r.get("normalized_status") or "UNKNOWN").upper()
        key = st.lower() if st.lower() in counts else "unknown"
        if key == "total":
            key = "unknown"
        counts[key] = counts.get(key, 0) + 1
        counts["total"] += 1
    parts = sum(counts[k] for k in ("active", "completed", "cancelled", "terminated", "suspended", "unknown"))
    return {
        "snapshot_total_contracts": counts["total"],
        "snapshot_active_contracts": counts["active"],
        "snapshot_completed_contracts": counts["completed"],
        "snapshot_cancelled_contracts": counts["cancelled"],
        "snapshot_terminated_contracts": counts["terminated"],
        "snapshot_suspended_contracts": counts["suspended"],
        "snapshot_unknown_status_contracts": counts["unknown"],
        "status_sum": parts,
        "status_sum_matches_total": parts == counts["total"],
        "lifecycle_classes_present": sorted(
            s for s in NORMALIZED_STATUSES if counts[s.lower()] > 0
        ),
    }


def lifecycle_gate_ok(recon: dict[str, Any]) -> dict[str, Any]:
    """PASS only with real ACTIVE + ≥1 closed class (COMPLETED/CANCELLED/TERMINATED/SUSPENDED)."""
    active = int(recon.get("snapshot_active_contracts") or 0)
    closed = sum(
        int(recon.get(k) or 0)
        for k in (
            "snapshot_completed_contracts",
            "snapshot_cancelled_contracts",
            "snapshot_terminated_contracts",
            "snapshot_suspended_contracts",
        )
    )
    has_active = active > 0
    has_closed = closed > 0
    ok = bool(recon.get("status_sum_matches_total") and has_active and has_closed)
    block = None
    if not has_active and not has_closed:
        block = "BLOCKED_SOURCE_DOES_NOT_PROVIDE_CONTRACT_LIFECYCLE"
    elif not has_closed:
        block = "BLOCKED_SOURCE_DOES_NOT_PROVIDE_CONTRACT_LIFECYCLE"
    elif not has_active:
        block = "BLOCKED_SOURCE_DOES_NOT_PROVIDE_CONTRACT_LIFECYCLE"
    elif not recon.get("status_sum_matches_total"):
        block = "BLOCKED_STATUS_RECONCILIATION_FAILED"
    return {
        "ok": ok,
        "has_active": has_active,
        "has_closed_lifecycle": has_closed,
        "block": block,
        "status": "PASS" if ok else (block or "FAIL"),
    }
