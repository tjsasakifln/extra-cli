"""#310 — official contract lifecycle events, append-only.

No official signal produces UNKNOWN, never a presumed absence.
Out-of-order events are folded deterministically. Dedup is idempotent
across sources via (source, source_event_id).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EVENT_FAMILIES: tuple[str, ...] = (
    "aditivo",
    "apostilamento",
    "suspensao",
    "rescisao",
    "cancelamento",
    "prorrogacao",
)

ContractAdminState = Literal["ACTIVE", "SUSPENDED", "RESCINDED", "CANCELLED", "UNKNOWN"]


@dataclass(frozen=True)
class ContractEvent:
    source: str
    source_event_id: str
    family: str
    effective_at: datetime
    published_at: datetime
    value_delta: float | None
    term_delta_days: int | None
    raw_hash: str
    run_id: str
    canonical_contract_id: str
    reverses_event_id: str | None = None


@dataclass(frozen=True)
class EventLedger:
    events: tuple[ContractEvent, ...]
    current_state: ContractAdminState
    reason: str


def classify_source_signal(events: list[ContractEvent]) -> ContractAdminState:
    if not events:
        return "UNKNOWN"
    return current_state(events)


def _sort_key(event: ContractEvent) -> tuple[datetime, datetime, str, str]:
    return (event.effective_at, event.published_at, event.source, event.source_event_id)


def append_event(ledger: EventLedger, event: ContractEvent) -> EventLedger:
    if event.family not in EVENT_FAMILIES:
        raise ValueError(f"unsupported_event_family:{event.family}")
    existing = {(item.source, item.source_event_id): item for item in ledger.events}
    key = (event.source, event.source_event_id)
    if key in existing:
        return ledger
    merged = tuple(sorted((*ledger.events, event), key=_sort_key))
    return EventLedger(events=merged, current_state=current_state(list(merged)), reason="applied")


def current_state(events: list[ContractEvent]) -> ContractAdminState:
    """Fold events in effective/published order. Reversals undo the named event."""
    if not events:
        return "UNKNOWN"
    reversed_ids = {event.reverses_event_id for event in events if event.reverses_event_id}
    state: ContractAdminState = "ACTIVE"
    for event in sorted(events, key=_sort_key):
        if event.source_event_id in reversed_ids:
            continue
        if event.family == "suspensao":
            state = "SUSPENDED"
        elif event.family == "rescisao":
            state = "RESCINDED"
        elif event.family == "cancelamento":
            state = "CANCELLED"
        elif event.family in {"aditivo", "apostilamento", "prorrogacao"}:
            if state == "UNKNOWN":
                state = "ACTIVE"
    return state


def empty_ledger() -> EventLedger:
    return EventLedger(events=(), current_state="UNKNOWN", reason="no_official_signal")
