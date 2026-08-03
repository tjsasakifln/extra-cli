"""Deterministic, auditável idempotency keys."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canon(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canon(value[k]) for k in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if hasattr(value, "value"):  # Enum
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def deterministic_key(namespace: str, payload: dict[str, Any]) -> str:
    """SHA-256 hex of namespace + canonical JSON payload (sorted keys)."""
    body = json.dumps(_canon(payload), ensure_ascii=False, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{namespace}|{body}".encode()).hexdigest()
    return f"{namespace}:{digest}"


def decision_idempotency_key(
    *,
    client_id: str,
    opportunity_key: str,
    human_decision: str,
    actor: str,
    justification: str,
    decided_at: str | None,
    evidence_hash: str | None,
    legacy_decision: str | None = None,
    supersedes_event_id: str | None = None,
    include_decided_at: bool = True,
) -> str:
    """Build a deterministic decision idempotency key.

    ``include_decided_at`` defaults True for CLI/historical imports (two intentional
    decisions at different times are distinct). Review-path retries must pass
    ``include_decided_at=False`` so wall-clock ``recorded_at`` does not fork a
    second event after CANONICAL_PERSISTED_PROJECTION_PARTIAL recovery.
    """
    payload: dict[str, Any] = {
        "client_id": client_id,
        "opportunity_key": opportunity_key,
        "human_decision": human_decision,
        "legacy_decision": legacy_decision,
        "actor": actor,
        "justification": justification,
        "evidence_hash": evidence_hash,
        "supersedes_event_id": supersedes_event_id,
    }
    if include_decided_at:
        payload["decided_at"] = decided_at
    return deterministic_key("dm.decision", payload)


def review_decision_idempotency_key(
    *,
    client_id: str,
    opportunity_key: str,
    human_decision: str,
    actor: str,
    justification: str,
    evidence_hash: str | None,
    run_id: str | None,
    legacy_decision: str | None = None,
) -> str:
    """Stable key for Extra review retries (excludes volatile wall-clock)."""
    return deterministic_key(
        "dm.decision.review",
        {
            "client_id": client_id,
            "opportunity_key": opportunity_key,
            "human_decision": human_decision,
            "legacy_decision": legacy_decision,
            "actor": actor,
            "justification": justification,
            "evidence_hash": evidence_hash,
            "run_id": run_id,
        },
    )


def action_idempotency_key(
    *,
    client_id: str,
    decision_event_id: str,
    description: str,
    owner: str | None,
    due_at: str | None,
    status: str,
    supersedes_event_id: str | None = None,
) -> str:
    return deterministic_key(
        "dm.action",
        {
            "client_id": client_id,
            "decision_event_id": decision_event_id,
            "description": description,
            "owner": owner,
            "due_at": due_at,
            "status": status,
            "supersedes_event_id": supersedes_event_id,
        },
    )


def outcome_idempotency_key(
    *,
    client_id: str,
    opportunity_key: str,
    outcome_type: str,
    observed_at: str,
    evidence_hash: str,
    source: str,
    supersedes_event_id: str | None = None,
) -> str:
    return deterministic_key(
        "dm.outcome",
        {
            "client_id": client_id,
            "opportunity_key": opportunity_key,
            "outcome_type": outcome_type,
            "observed_at": observed_at,
            "evidence_hash": evidence_hash,
            "source": source,
            "supersedes_event_id": supersedes_event_id,
        },
    )
