"""Local artifact projections (never canonical when PG is enabled)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.decision_memory.mapping import HUMAN_TO_LEGACY
from scripts.decision_memory.models import HumanDecision

LEDGER_NAME = "human-decisions.jsonl"
PERSISTENCE_META = "decision-memory-persistence.json"


def event_to_legacy_ledger_row(event: dict[str, Any]) -> dict[str, Any]:
    """Project a canonical decision event to the legacy human-decisions.jsonl shape."""
    human = event.get("human_decision")
    legacy = event.get("legacy_decision")
    if not legacy and human:
        try:
            legacy = HUMAN_TO_LEGACY[HumanDecision(human)].value
        except (KeyError, ValueError):
            legacy = "UNKNOWN"
    return {
        "schema": "extra-decision-review/1.0",
        "recorded_at": event.get("decided_at") or event.get("created_at"),
        "actor": event.get("actor"),
        "opportunity_id": event.get("opportunity_key"),
        "decision": legacy,
        "canonical_decision": human,
        "reason": event.get("justification"),
        "next_action": (event.get("payload") or {}).get("next_action"),
        "next_action_due": (event.get("payload") or {}).get("next_action_due"),
        "profile_version": event.get("profile_version"),
        "profile_hash": event.get("profile_hash"),
        "evidence_hash": event.get("evidence_hash"),
        "run_dir": (event.get("payload") or {}).get("run_dir"),
        "canonical_event_id": event.get("event_id"),
        "idempotency_key": event.get("idempotency_key"),
        "persistence": "CANONICAL_POSTGRES_PROJECTION",
        "temporal_integrity": event.get("temporal_integrity"),
    }


def append_projection(run_dir: Path, event: dict[str, Any]) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / LEDGER_NAME
    row = event_to_legacy_ledger_row(event)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    meta = {
        "schema": "decision-memory-persistence/1.0",
        "status": "CANONICAL_PERSISTED",
        "last_event_id": event.get("event_id"),
        "client_id": event.get("client_id"),
        "idempotency_key": event.get("idempotency_key"),
    }
    (run_dir / PERSISTENCE_META).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_partial_projection_failure(run_dir: Path, *, event_id: str, client_id: str, error: str) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / PERSISTENCE_META
    meta = {
        "schema": "decision-memory-persistence/1.0",
        "status": "CANONICAL_PERSISTED_PROJECTION_PARTIAL",
        "last_event_id": event_id,
        "client_id": client_id,
        "projection_error": error,
        "recoverable": True,
        "hint": "Retry projection; PG event is authoritative; import is idempotent",
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
