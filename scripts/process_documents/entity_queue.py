"""Operational entity queue for daily process-document collection.

Replaces sticky “first N” selection with a rotating queue keyed by **last valid
success** (not merely last attempt). Each entity tracks:

- next_run_at
- last_attempt_at
- last_success_at
- consecutive_failures / attempt_count
- last_status / sources

SLA: any active entity without a valid collection within ``SLA_HOURS`` is
reported as an alert. Drain mode keeps selecting overdue entities until lag is
cleared or capacity (batch/time budget) is exhausted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus
from scripts.process_documents.storage import ensure_roots, write_json

SLA_HOURS = 24
QUEUE_CHECKPOINT_REL = Path("checkpoints") / "entity_queue.json"
VALID_SUCCESS = frozenset(
    {
        DocumentRunStatus.SUCCESS_NONZERO.value,
        DocumentRunStatus.SUCCESS_ZERO.value,
    }
)

# Partial with at least one successful source still counts as valid for SLA/queue.
def _is_valid_collection(status: str | None, result: Mapping[str, Any] | None = None) -> bool:
    if status in VALID_SUCCESS:
        return True
    if status == DocumentRunStatus.PARTIAL.value and result:
        srcs = result.get("source_results") or {}
        if isinstance(srcs, dict):
            return any(
                isinstance(v, dict) and v.get("status") in VALID_SUCCESS for v in srcs.values()
            )
    return False


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    text = str(ts).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@dataclass
class EntityQueueEntry:
    canonical_id: str
    next_run_at: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    consecutive_failures: int = 0
    attempt_count: int = 0
    last_status: str | None = None
    sources: list[str] = field(default_factory=list)
    last_error: str | None = None

    def lag_hours(self, now: datetime | None = None) -> float | None:
        """Hours since last valid success; None if never succeeded (infinite lag)."""
        success = _parse_iso(self.last_success_at)
        if success is None:
            return None
        clock = now or _now()
        return max(0.0, (clock - success).total_seconds() / 3600.0)

    def is_overdue(self, *, sla_hours: float = SLA_HOURS, now: datetime | None = None) -> bool:
        clock = now or _now()
        next_run = _parse_iso(self.next_run_at)
        if next_run is not None and next_run <= clock:
            return True
        lag = self.lag_hours(clock)
        if lag is None:
            return True  # never succeeded → overdue
        return lag >= sla_hours

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EntityQueueEntry:
        return cls(
            canonical_id=str(data.get("canonical_id") or data.get("id") or ""),
            next_run_at=data.get("next_run_at"),
            last_attempt_at=data.get("last_attempt_at") or data.get("last_visited_at"),
            last_success_at=data.get("last_success_at"),
            consecutive_failures=int(data.get("consecutive_failures") or 0),
            attempt_count=int(data.get("attempt_count") or 0),
            last_status=data.get("last_status"),
            sources=list(data.get("sources") or []),
            last_error=data.get("last_error"),
        )


def queue_path(meta_root: Path | None = None) -> Path:
    _, meta = ensure_roots(meta_root=meta_root)
    return meta / QUEUE_CHECKPOINT_REL


def load_entity_queue(meta_root: Path | None = None) -> dict[str, EntityQueueEntry]:
    path = queue_path(meta_root=meta_root)
    # Migrate legacy visits checkpoint if queue missing
    if not path.is_file():
        legacy = path.parent / "incremental_visits.json"
        if legacy.is_file():
            return _migrate_legacy_visits(legacy)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, dict):
        return {}
    out: dict[str, EntityQueueEntry] = {}
    for cid, payload in entities.items():
        if isinstance(payload, str):
            out[str(cid)] = EntityQueueEntry(
                canonical_id=str(cid),
                last_attempt_at=payload,
                last_success_at=payload,
            )
        elif isinstance(payload, dict):
            entry = EntityQueueEntry.from_dict({**payload, "canonical_id": cid})
            out[str(cid)] = entry
    return out


def _migrate_legacy_visits(legacy_path: Path) -> dict[str, EntityQueueEntry]:
    try:
        data = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entities = data.get("entities") if isinstance(data, dict) else {}
    out: dict[str, EntityQueueEntry] = {}
    if not isinstance(entities, dict):
        return out
    for cid, payload in entities.items():
        if isinstance(payload, str):
            out[str(cid)] = EntityQueueEntry(
                canonical_id=str(cid),
                last_attempt_at=payload,
                # Legacy only tracked attempt — do not invent success
            )
        elif isinstance(payload, dict):
            ts = payload.get("last_visited_at")
            st = payload.get("last_status")
            success = ts if st in VALID_SUCCESS else None
            out[str(cid)] = EntityQueueEntry(
                canonical_id=str(cid),
                last_attempt_at=ts,
                last_success_at=success,
                last_status=st,
                sources=list(payload.get("sources") or []),
                attempt_count=1 if ts else 0,
            )
    return out


def save_entity_queue(
    queue: Mapping[str, EntityQueueEntry],
    *,
    meta_root: Path | None = None,
    updated_at: str | None = None,
) -> Path:
    path = queue_path(meta_root=meta_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = updated_at or _now().isoformat()
    payload = {
        "updated_at": stamp,
        "sla_hours": SLA_HOURS,
        "entities": {cid: e.to_dict() for cid, e in sorted(queue.items())},
    }
    write_json(path, payload)
    return path


def ensure_entries(
    queue: dict[str, EntityQueueEntry],
    entity_ids: Sequence[str],
) -> dict[str, EntityQueueEntry]:
    for cid in entity_ids:
        if cid not in queue:
            queue[cid] = EntityQueueEntry(canonical_id=cid)
    return queue


def apply_attempt_result(
    entry: EntityQueueEntry,
    *,
    status: str | None,
    sources: Sequence[str] | None = None,
    error: str | None = None,
    attempted_at: datetime | None = None,
    sla_hours: float = SLA_HOURS,
    result: Mapping[str, Any] | None = None,
) -> EntityQueueEntry:
    """Update queue entry after one collection attempt (pure)."""
    clock = attempted_at or _now()
    entry.last_attempt_at = _iso(clock)
    entry.attempt_count = int(entry.attempt_count or 0) + 1
    entry.last_status = status
    if sources is not None:
        entry.sources = list(sources)
    if error:
        entry.last_error = error
    valid = _is_valid_collection(status, result)
    if valid:
        entry.last_success_at = _iso(clock)
        entry.consecutive_failures = 0
        entry.next_run_at = _iso(clock + timedelta(hours=sla_hours))
        entry.last_error = None
    else:
        entry.consecutive_failures = int(entry.consecutive_failures or 0) + 1
        # Retry sooner after failure: min(4h * failures, sla_hours)
        backoff_h = min(sla_hours, max(1.0, 4.0 * entry.consecutive_failures))
        entry.next_run_at = _iso(clock + timedelta(hours=backoff_h))
    return entry


def select_batch_by_success_lag(
    targets: Sequence[EntityDocumentDiscovery],
    queue: Mapping[str, EntityQueueEntry],
    *,
    limit: int | None,
    now: datetime | None = None,
    sla_hours: float = SLA_HOURS,
) -> list[EntityDocumentDiscovery]:
    """Select entities ordered by greatest success lag (never-success first).

    Primary key: never had last_success_at.
    Secondary: oldest last_success_at.
    Tertiary: next_run_at overdue first.
    Tie-break: canonical_id.
    """
    def sort_key(d: EntityDocumentDiscovery) -> tuple[int, datetime, datetime, str]:
        e = queue.get(d.canonical_id) or EntityQueueEntry(canonical_id=d.canonical_id)
        success = _parse_iso(e.last_success_at)
        next_run = _parse_iso(e.next_run_at) or datetime.min.replace(tzinfo=UTC)
        if success is None:
            return (0, datetime.min.replace(tzinfo=UTC), next_run, d.canonical_id)
        return (1, success, next_run, d.canonical_id)

    _ = now  # reserved for lag metrics / future overdue filters
    ordered = sorted(targets, key=sort_key)
    if limit is not None:
        return ordered[:limit]
    return ordered


def overdue_entities(
    targets: Sequence[EntityDocumentDiscovery],
    queue: Mapping[str, EntityQueueEntry],
    *,
    now: datetime | None = None,
    sla_hours: float = SLA_HOURS,
) -> list[EntityDocumentDiscovery]:
    clock = now or _now()
    out: list[EntityDocumentDiscovery] = []
    for d in targets:
        e = queue.get(d.canonical_id) or EntityQueueEntry(canonical_id=d.canonical_id)
        if e.is_overdue(sla_hours=sla_hours, now=clock):
            out.append(d)
    return out


def build_sla_alerts(
    targets: Sequence[EntityDocumentDiscovery],
    queue: Mapping[str, EntityQueueEntry],
    *,
    now: datetime | None = None,
    sla_hours: float = SLA_HOURS,
) -> list[dict[str, Any]]:
    """Alert when any active entity exceeds SLA without valid collection."""
    clock = now or _now()
    alerts: list[dict[str, Any]] = []
    for d in targets:
        e = queue.get(d.canonical_id) or EntityQueueEntry(canonical_id=d.canonical_id)
        lag = e.lag_hours(clock)
        never = lag is None
        hours = float("inf") if never else float(lag)
        if never or hours >= sla_hours:
            alerts.append(
                {
                    "severity": "critical" if never or hours >= sla_hours * 2 else "warning",
                    "canonical_id": d.canonical_id,
                    "razao_social": d.razao_social,
                    "sla_hours": sla_hours,
                    "lag_hours": None if never else round(hours, 3),
                    "never_succeeded": never,
                    "last_success_at": e.last_success_at,
                    "last_attempt_at": e.last_attempt_at,
                    "last_status": e.last_status,
                    "consecutive_failures": e.consecutive_failures,
                    "attempt_count": e.attempt_count,
                    "next_run_at": e.next_run_at,
                    "message": (
                        f"Active entity {d.canonical_id} has no valid collection "
                        f"within {sla_hours}h SLA"
                        + (" (never succeeded)" if never else f" (lag={hours:.1f}h)")
                    ),
                    "next_action": "enqueue for multi-source collect and inspect source errors",
                }
            )
    alerts.sort(key=lambda a: (0 if a["never_succeeded"] else 1, -(a["lag_hours"] or 1e18)))
    return alerts


def queue_summary(
    targets: Sequence[EntityDocumentDiscovery],
    queue: Mapping[str, EntityQueueEntry],
    *,
    now: datetime | None = None,
    sla_hours: float = SLA_HOURS,
) -> dict[str, Any]:
    clock = now or _now()
    overdue = overdue_entities(targets, queue, now=clock, sla_hours=sla_hours)
    never = 0
    ok = 0
    for d in targets:
        e = queue.get(d.canonical_id) or EntityQueueEntry(canonical_id=d.canonical_id)
        if e.last_success_at is None:
            never += 1
        elif not e.is_overdue(sla_hours=sla_hours, now=clock):
            ok += 1
    return {
        "eligible_count": len(targets),
        "overdue_count": len(overdue),
        "never_succeeded_count": never,
        "within_sla_count": ok,
        "sla_hours": sla_hours,
        "lag_cleared": len(overdue) == 0 and len(targets) > 0,
        "generated_at": clock.isoformat(),
    }


def drain_decision(
    *,
    overdue_remaining: int,
    batches_done: int,
    entities_done: int,
    max_batches: int | None,
    max_entities: int | None,
    wall_seconds: float,
    max_wall_seconds: float | None,
) -> tuple[bool, str]:
    """Return (stop, reason). Pure capacity / lag decision for drain loop."""
    if overdue_remaining <= 0:
        return True, "lag_cleared"
    if max_batches is not None and batches_done >= max_batches:
        return True, "capacity_insufficient_batches"
    if max_entities is not None and entities_done >= max_entities:
        return True, "capacity_insufficient_entities"
    if max_wall_seconds is not None and wall_seconds >= max_wall_seconds:
        return True, "capacity_insufficient_wall_time"
    return False, "continue"
