"""Persist Warmbly outcomes into Decision & Outcome Memory (no parallel ledger)."""

from __future__ import annotations

from typing import Any, Protocol

from scripts.decision_memory.models import OutcomeRecordInput
from scripts.warmbly_bridge.outcome_mapping import (
    OutcomeValidationError,
    build_outcome_record_input,
    suggested_commercial_state,
)


class OutcomeStore(Protocol):
    def record_outcome(self, inp: OutcomeRecordInput) -> dict[str, Any]: ...

    def get_outcome_by_idempotency(self, client_id: str, key: str) -> dict[str, Any] | None: ...


class InMemoryOutcomeStore:
    """Test/dev store implementing the same idempotent contract as DM repository."""

    def __init__(self) -> None:
        self.by_idem: dict[tuple[str, str], dict[str, Any]] = {}
        self.rows: list[dict[str, Any]] = []

    def record_outcome(self, inp: OutcomeRecordInput) -> dict[str, Any]:
        key = (inp.client_id, inp.idempotency_key or "")
        if key[1] and key in self.by_idem:
            return {"status": "duplicate", "event": self.by_idem[key], "created": False}
        event = {
            "event_id": f"mem-{len(self.rows) + 1}",
            "client_id": inp.client_id,
            "opportunity_key": inp.opportunity_key,
            "outcome_type": inp.outcome_type.value if hasattr(inp.outcome_type, "value") else inp.outcome_type,
            "idempotency_key": inp.idempotency_key,
            "structured_facts": dict(inp.structured_facts),
            "source": inp.source,
            "actor": inp.actor,
            "observed_at": inp.observed_at.isoformat().replace("+00:00", "Z"),
            "payload": dict(inp.payload),
        }
        self.rows.append(event)
        if key[1]:
            self.by_idem[key] = event
        return {"status": "created", "event": event, "created": True}

    def get_outcome_by_idempotency(self, client_id: str, key: str) -> dict[str, Any] | None:
        return self.by_idem.get((client_id, key))


class DecisionMemoryOutcomeStore:
    """Adapter over DecisionMemoryRepository."""

    def __init__(self, repo: Any) -> None:
        self.repo = repo

    def record_outcome(self, inp: OutcomeRecordInput) -> dict[str, Any]:
        return self.repo.record_outcome(inp)

    def get_outcome_by_idempotency(self, client_id: str, key: str) -> dict[str, Any] | None:
        return self.repo._get_outcome_by_idem(client_id, key)  # noqa: SLF001 — intentional adapter


def persist_outcome(
    envelope: dict[str, Any],
    *,
    store: OutcomeStore,
    client_id: str,
    actor: str = "warmbly-outcome-receptor",
) -> dict[str, Any]:
    """Validate + map + persist. Returns status dict; never raises for duplicates."""
    try:
        inp = build_outcome_record_input(envelope, client_id=client_id, actor=actor)
    except OutcomeValidationError:
        raise
    result = store.record_outcome(inp)
    event_type = str(envelope.get("event_type") or "").upper()
    return {
        "ok": True,
        "created": bool(result.get("created")),
        "status": result.get("status"),
        "idempotency_key": inp.idempotency_key,
        "opportunity_key": inp.opportunity_key,
        "dm_outcome_type": inp.outcome_type.value,
        "suggested_commercial_state": suggested_commercial_state(
            # use normalized type from structured facts when available
            str((inp.structured_facts or {}).get("warmbly_event_type") or event_type)
        ),
        "event": result.get("event"),
    }
