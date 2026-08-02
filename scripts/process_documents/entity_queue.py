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
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.process_documents.error_classes import (
    ErrorClass,
    classify_error,
    is_retryable,
    should_dead_letter,
    should_open_circuit,
)
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus
from scripts.process_documents.storage import ensure_roots, write_json

SLA_HOURS = 24
QUEUE_CHECKPOINT_REL = Path("checkpoints") / "entity_queue.json"
DLQ_REL = Path("checkpoints") / "entity_source_dlq.jsonl"
CB_FAILURE_THRESHOLD = 5
CB_COOLDOWN_HOURS = 2.0
BACKOFF_BASE_HOURS = 1.0
BACKOFF_MAX_HOURS = 24.0
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
            return any(isinstance(v, dict) and v.get("status") in VALID_SUCCESS for v in srcs.values())
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
class SourceQueueEntry:
    """Operational state for one (canonical_entity_id × source_id).

    Independent of sibling sources on the same entity. Persisted fields cover
    scheduling, observability, circuit breaker and resume checkpoints.
    """

    canonical_id: str
    source_id: str
    next_run_at: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    consecutive_failures: int = 0
    attempt_count: int = 0
    last_status: str | None = None
    last_error: str | None = None
    error_class: str = ErrorClass.NONE.value
    duration_ms: int | None = None
    documents_found: int = 0
    documents_new: int = 0
    documents_changed: int = 0
    cursor: str | None = None  # opaque checkpoint for resume
    circuit_breaker_state: str = "closed"  # closed | open | half_open
    circuit_open_until: str | None = None
    dead_letter: bool = False
    dead_letter_reason: str | None = None
    criticality: int = 5  # 1=highest, 10=lowest
    scope_complete: bool | None = None

    def lag_hours(self, now: datetime | None = None) -> float | None:
        success = _parse_iso(self.last_success_at)
        if success is None:
            return None
        clock = now or _now()
        return max(0.0, (clock - success).total_seconds() / 3600.0)

    def is_circuit_open(self, now: datetime | None = None) -> bool:
        if self.circuit_breaker_state != "open":
            return False
        until = _parse_iso(self.circuit_open_until)
        clock = now or _now()
        if until is None:
            return True
        if until <= clock:
            # cooldown elapsed — half-open allows one probe
            self.circuit_breaker_state = "half_open"
            return False
        return True

    def is_overdue(self, *, sla_hours: float = SLA_HOURS, now: datetime | None = None) -> bool:
        clock = now or _now()
        if self.dead_letter:
            return False
        if self.is_circuit_open(clock):
            return False
        next_run = _parse_iso(self.next_run_at)
        if next_run is not None and next_run <= clock:
            return True
        lag = self.lag_hours(clock)
        if lag is None:
            return True
        return lag >= sla_hours

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceQueueEntry:
        return cls(
            canonical_id=str(data.get("canonical_id") or ""),
            source_id=str(data.get("source_id") or ""),
            next_run_at=data.get("next_run_at"),
            last_attempt_at=data.get("last_attempt_at"),
            last_success_at=data.get("last_success_at"),
            consecutive_failures=int(data.get("consecutive_failures") or 0),
            attempt_count=int(data.get("attempt_count") or 0),
            last_status=data.get("last_status"),
            last_error=data.get("last_error"),
            error_class=str(data.get("error_class") or ErrorClass.NONE.value),
            duration_ms=int(data["duration_ms"]) if data.get("duration_ms") is not None else None,
            documents_found=int(data.get("documents_found") or 0),
            documents_new=int(data.get("documents_new") or 0),
            documents_changed=int(data.get("documents_changed") or 0),
            cursor=data.get("cursor"),
            circuit_breaker_state=str(data.get("circuit_breaker_state") or "closed"),
            circuit_open_until=data.get("circuit_open_until"),
            dead_letter=bool(data.get("dead_letter") or False),
            dead_letter_reason=data.get("dead_letter_reason"),
            criticality=int(data.get("criticality") or 5),
            scope_complete=data.get("scope_complete"),
        )


def source_key(canonical_id: str, source_id: str) -> str:
    return f"{canonical_id}\x1f{source_id}"


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
    # entity × source operational state (never masked by sibling success)
    sources_state: dict[str, SourceQueueEntry] = field(default_factory=dict)

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

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EntityQueueEntry:
        raw_ss = data.get("sources_state") or {}
        sources_state: dict[str, SourceQueueEntry] = {}
        if isinstance(raw_ss, dict):
            for sid, payload in raw_ss.items():
                if isinstance(payload, dict):
                    sources_state[str(sid)] = SourceQueueEntry.from_dict(
                        {**payload, "canonical_id": data.get("canonical_id") or data.get("id") or "", "source_id": sid}
                    )
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
            sources_state=sources_state,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # asdict nests SourceQueueEntry already; ensure source keys stable
        ss = {}
        for sid, se in (self.sources_state or {}).items():
            ss[str(sid)] = se.to_dict() if hasattr(se, "to_dict") else dict(se)
        d["sources_state"] = ss
        return d


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

    def sort_key(d: EntityDocumentDiscovery) -> tuple[int, int, datetime, datetime, str]:
        e = queue.get(d.canonical_id) or EntityQueueEntry(canonical_id=d.canonical_id)
        success = _parse_iso(e.last_success_at)
        next_run = _parse_iso(e.next_run_at) or datetime.min.replace(tzinfo=UTC)
        # Prefer entities that can be cleared via local/open sources (CIGA/DOM/SC)
        # before PNCP-heavy ones, so rate-limited PNCP does not starve lag drain.
        plats = {str(p).lower() for p in (getattr(d, "platforms", None) or [])}
        healthy_pref = 0 if plats & {"ciga_ckan", "ciga_dom", "dom_sc", "sc_compras"} else 1
        if success is None:
            return (0, healthy_pref, datetime.min.replace(tzinfo=UTC), next_run, d.canonical_id)
        return (1, healthy_pref, success, next_run, d.canonical_id)

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
                        f"within {sla_hours}h SLA" + (" (never succeeded)" if never else f" (lag={hours:.1f}h)")
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
    max_requests: int | None = None,
    requests_done: int = 0,
) -> tuple[bool, str]:
    """Return (stop, reason). Pure capacity / lag decision for drain loop.

    Capacity exhaustion reasons map to operational status PARTIAL_CAPACITY_EXHAUSTED.
    """
    if overdue_remaining <= 0:
        return True, "lag_cleared"
    if max_batches is not None and batches_done >= max_batches:
        return True, "PARTIAL_CAPACITY_EXHAUSTED"
    if max_entities is not None and entities_done >= max_entities:
        return True, "PARTIAL_CAPACITY_EXHAUSTED"
    if max_wall_seconds is not None and wall_seconds >= max_wall_seconds:
        return True, "PARTIAL_CAPACITY_EXHAUSTED"
    if max_requests is not None and requests_done >= max_requests:
        return True, "PARTIAL_CAPACITY_EXHAUSTED"
    return False, "continue"


def get_source_entry(
    queue: Mapping[str, EntityQueueEntry],
    canonical_id: str,
    source_id: str,
) -> SourceQueueEntry:
    ent = queue.get(canonical_id) or EntityQueueEntry(canonical_id=canonical_id)
    se = (ent.sources_state or {}).get(source_id)
    if se is None:
        return SourceQueueEntry(canonical_id=canonical_id, source_id=source_id)
    return se


def compute_backoff_hours(
    consecutive_failures: int,
    *,
    base_hours: float = BACKOFF_BASE_HOURS,
    max_hours: float = BACKOFF_MAX_HOURS,
    jitter: bool = True,
    rng: random.Random | None = None,
) -> float:
    """Exponential backoff with optional full-jitter (AWS-style)."""
    exp = min(max_hours, base_hours * (2 ** max(0, consecutive_failures - 1)))
    if not jitter:
        return exp
    r = rng or random.Random()  # noqa: S311 — scheduling jitter, not crypto
    return r.uniform(0.0, exp)  # noqa: S311 — scheduling jitter, not crypto


def apply_source_attempt_result(
    entry: SourceQueueEntry,
    *,
    status: str | None,
    error: str | None = None,
    attempted_at: datetime | None = None,
    sla_hours: float = SLA_HOURS,
    scope_complete: bool | None = None,
    duration_ms: int | None = None,
    documents_found: int | None = None,
    documents_new: int | None = None,
    documents_changed: int | None = None,
    cursor: str | None = None,
    http_status: int | None = None,
    error_class: str | ErrorClass | None = None,
    cb_threshold: int = CB_FAILURE_THRESHOLD,
    cb_cooldown_hours: float = CB_COOLDOWN_HOURS,
    rng: random.Random | None = None,
) -> SourceQueueEntry:
    """Update one entity×source entry. Sibling sources are never modified here."""
    clock = attempted_at or _now()
    entry.last_attempt_at = _iso(clock)
    entry.attempt_count = int(entry.attempt_count or 0) + 1
    entry.last_status = status
    if error:
        entry.last_error = error
    if duration_ms is not None:
        entry.duration_ms = int(duration_ms)
    if documents_found is not None:
        entry.documents_found = int(documents_found)
    if documents_new is not None:
        entry.documents_new = int(documents_new)
    if documents_changed is not None:
        entry.documents_changed = int(documents_changed)
    if cursor is not None:
        entry.cursor = cursor
    if scope_complete is not None:
        entry.scope_complete = bool(scope_complete)
    # Budget skip is not a success and not a hard failure for consecutive_failures
    if status in (
        DocumentRunStatus.NOT_QUERIED_BUDGET.value,
        DocumentRunStatus.NOT_QUERIED.value,
    ):
        entry.error_class = ErrorClass.CAPACITY.value
        return entry
    valid = status in VALID_SUCCESS and (
        status != DocumentRunStatus.SUCCESS_ZERO.value or entry.scope_complete is not False
    )
    # SUCCESS_ZERO without scope_complete must not clear lag
    if status == DocumentRunStatus.SUCCESS_ZERO.value and entry.scope_complete is False:
        valid = False
    if valid:
        entry.last_success_at = _iso(clock)
        entry.consecutive_failures = 0
        entry.next_run_at = _iso(clock + timedelta(hours=sla_hours))
        entry.last_error = None
        entry.error_class = ErrorClass.NONE.value
        entry.circuit_breaker_state = "closed"
        entry.circuit_open_until = None
        entry.dead_letter = False
        entry.dead_letter_reason = None
    else:
        entry.consecutive_failures = int(entry.consecutive_failures or 0) + 1
        cls = (
            ErrorClass(str(error_class))
            if error_class is not None
            else classify_error(status=status, error=error, http_status=http_status)
        )
        entry.error_class = cls.value
        backoff_h = compute_backoff_hours(entry.consecutive_failures, rng=rng)
        if cls == ErrorClass.RATE_LIMIT:
            backoff_h = max(backoff_h, 0.5)
        entry.next_run_at = _iso(clock + timedelta(hours=min(sla_hours, max(backoff_h, 0.05))))
        if should_open_circuit(cls) and entry.consecutive_failures >= cb_threshold:
            entry.circuit_breaker_state = "open"
            entry.circuit_open_until = _iso(clock + timedelta(hours=cb_cooldown_hours))
        if should_dead_letter(cls, entry.consecutive_failures):
            entry.dead_letter = True
            entry.dead_letter_reason = f"{cls.value}:{status or error or 'unknown'}"
    return entry


def apply_multi_source_attempt(
    entity_entry: EntityQueueEntry,
    *,
    source_results: Mapping[str, Mapping[str, Any]],
    attempted_at: datetime | None = None,
    sla_hours: float = SLA_HOURS,
    aggregate_status: str | None = None,
) -> EntityQueueEntry:
    """Apply per-source results; entity aggregate does not wipe failed sources.

    - Each source gets its own last_success_at / consecutive_failures.
    - Entity last_success_at advances only when ALL consulted (non-NOT_QUERIED*)
      sources are valid successes.
    - Failed sources remain overdue; successful ones get next_run_at = now+SLA.
    """
    clock = attempted_at or _now()
    entity_entry.last_attempt_at = _iso(clock)
    entity_entry.attempt_count = int(entity_entry.attempt_count or 0) + 1
    entity_entry.last_status = aggregate_status
    entity_entry.sources = sorted(source_results.keys())

    if entity_entry.sources_state is None:
        entity_entry.sources_state = {}

    consulted_ok = True
    any_consulted = False
    for sid, rd in source_results.items():
        st = rd.get("status")
        se = entity_entry.sources_state.get(sid) or SourceQueueEntry(
            canonical_id=entity_entry.canonical_id, source_id=sid
        )
        err_raw = rd.get("errors")
        if isinstance(err_raw, list) and err_raw:
            err_msg = err_raw[0]
        else:
            err_msg = rd.get("error")
        se = apply_source_attempt_result(
            se,
            status=st if isinstance(st, str) else (st.value if st is not None else None),
            error=str(err_msg) if err_msg else None,
            attempted_at=clock,
            sla_hours=sla_hours,
            scope_complete=rd.get("scope_complete"),
            duration_ms=rd.get("duration_ms"),
            documents_found=rd.get("documents_found") or rd.get("documents_downloaded"),
            documents_new=rd.get("documents_new"),
            documents_changed=rd.get("documents_changed"),
            cursor=rd.get("cursor") or rd.get("checkpoint"),
            http_status=rd.get("http_status"),
            error_class=rd.get("error_class"),
        )
        entity_entry.sources_state[sid] = se
        if se.dead_letter:
            # DLQ append is optional here (no meta_root); callers may persist
            pass
        if st in (
            DocumentRunStatus.NOT_QUERIED_BUDGET.value,
            DocumentRunStatus.NOT_QUERIED.value,
            "NOT_QUERIED_BUDGET",
            "NOT_QUERIED",
        ):
            continue
        any_consulted = True
        valid = _is_valid_collection(
            st if isinstance(st, str) else None,
            rd,
        )
        if st == DocumentRunStatus.SUCCESS_ZERO.value and rd.get("scope_complete") is False:
            valid = False
        if not valid:
            consulted_ok = False

    if any_consulted and consulted_ok:
        entity_entry.last_success_at = _iso(clock)
        entity_entry.consecutive_failures = 0
        entity_entry.next_run_at = _iso(clock + timedelta(hours=sla_hours))
        entity_entry.last_error = None
    elif any_consulted:
        entity_entry.consecutive_failures = int(entity_entry.consecutive_failures or 0) + 1
        backoff_h = min(sla_hours, max(1.0, 4.0 * entity_entry.consecutive_failures))
        entity_entry.next_run_at = _iso(clock + timedelta(hours=backoff_h))
        # Do NOT set last_success_at — partial/mixed keeps lag
    return entity_entry


def max_source_lag_hours(
    entry: EntityQueueEntry,
    *,
    now: datetime | None = None,
    applicable_sources: Sequence[str] | None = None,
) -> float | None:
    """Greatest lag among applicable sources; None if any never succeeded."""
    clock = now or _now()
    srcs = list(applicable_sources) if applicable_sources is not None else list((entry.sources_state or {}).keys())
    if not srcs:
        return entry.lag_hours(clock)
    lags: list[float | None] = []
    for sid in srcs:
        se = (entry.sources_state or {}).get(sid) or SourceQueueEntry(canonical_id=entry.canonical_id, source_id=sid)
        lags.append(se.lag_hours(clock))
    if any(x is None for x in lags):
        return None
    return max(float(x) for x in lags)  # type: ignore[arg-type]


def select_batch_by_source_lag(
    targets: Sequence[EntityDocumentDiscovery],
    queue: Mapping[str, EntityQueueEntry],
    *,
    sources_for_entity: Mapping[str, Sequence[str]] | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[EntityDocumentDiscovery]:
    """Prefer entities with the greatest per-source lag (entity×source aware)."""
    clock = now or _now()

    def sort_key(d: EntityDocumentDiscovery) -> tuple[int, int, float, str]:
        e = queue.get(d.canonical_id) or EntityQueueEntry(canonical_id=d.canonical_id)
        applicable = None
        if sources_for_entity is not None:
            applicable = list(sources_for_entity.get(d.canonical_id) or [])
        lag = max_source_lag_hours(e, now=clock, applicable_sources=applicable)
        # Prefer entities clearable via open/local sources before PNCP (rate-limit).
        plats = {str(p).lower() for p in (getattr(d, "platforms", None) or [])}
        healthy_pref = 0 if plats & {"ciga_ckan", "ciga_dom", "dom_sc", "sc_compras"} else 1
        if lag is None:
            return (0, healthy_pref, 1e18, d.canonical_id)  # never — highest priority
        return (1, healthy_pref, -float(lag), d.canonical_id)

    ordered = sorted(targets, key=sort_key)
    if limit is not None:
        return ordered[:limit]
    return ordered


def ensure_entity_source_pairs(
    queue: dict[str, EntityQueueEntry],
    entity_sources: Mapping[str, Sequence[str]],
    *,
    criticality: Mapping[str, int] | None = None,
) -> dict[str, EntityQueueEntry]:
    """Ensure every active entity×source has independent persisted state."""
    for cid, sources in entity_sources.items():
        ent = queue.get(cid) or EntityQueueEntry(canonical_id=cid)
        if ent.sources_state is None:
            ent.sources_state = {}
        for sid in sources:
            if sid not in ent.sources_state:
                ent.sources_state[sid] = SourceQueueEntry(
                    canonical_id=cid,
                    source_id=sid,
                    criticality=int((criticality or {}).get(cid, 5)),
                )
            if sid not in ent.sources:
                ent.sources = sorted(set(ent.sources) | {sid})
        queue[cid] = ent
    return queue


def list_source_pairs(
    queue: Mapping[str, EntityQueueEntry],
    entity_sources: Mapping[str, Sequence[str]],
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for cid, sources in sorted(entity_sources.items()):
        for sid in sources:
            pairs.append((cid, sid))
    return pairs


def select_source_pairs_by_lag(
    queue: Mapping[str, EntityQueueEntry],
    entity_sources: Mapping[str, Sequence[str]],
    *,
    limit: int | None = None,
    now: datetime | None = None,
    sla_hours: float = SLA_HOURS,
    skip_dead_letter: bool = True,
    skip_open_circuit: bool = True,
) -> list[SourceQueueEntry]:
    """Select entity×source pairs by lag then criticality (never static prefix).

    Ensures that a batch limit never permanently starves later pairs: order is
    by (never_success, -lag, criticality, id), so each cycle rotates.
    """
    clock = now or _now()
    candidates: list[SourceQueueEntry] = []
    for cid, sources in entity_sources.items():
        ent = queue.get(cid) or EntityQueueEntry(canonical_id=cid)
        for sid in sources:
            se = (ent.sources_state or {}).get(sid) or SourceQueueEntry(canonical_id=cid, source_id=sid)
            if skip_dead_letter and se.dead_letter:
                continue
            if skip_open_circuit and se.is_circuit_open(clock):
                continue
            candidates.append(se)

    def sort_key(se: SourceQueueEntry) -> tuple[int, float, int, str, str]:
        lag = se.lag_hours(clock)
        never = 0 if lag is None else 1
        lag_val = 1e18 if lag is None else float(lag)
        # overdue next_run gets slight boost via negative lag if needed
        next_run = _parse_iso(se.next_run_at)
        overdue_boost = 0.0
        if next_run is not None and next_run <= clock:
            overdue_boost = 0.1
        return (never, -(lag_val + overdue_boost), int(se.criticality or 5), se.canonical_id, se.source_id)

    ordered = sorted(candidates, key=sort_key)
    if limit is not None:
        return ordered[: int(limit)]
    return ordered


def reprocess_selection(
    queue: dict[str, EntityQueueEntry],
    *,
    entity_ids: Sequence[str] | None = None,
    source_ids: Sequence[str] | None = None,
    clear_dead_letter: bool = True,
    clear_circuit: bool = True,
    now: datetime | None = None,
) -> int:
    """Selective reprocess: reset next_run and optional DLQ/CB for matching pairs."""
    clock = now or _now()
    n = 0
    for cid, ent in queue.items():
        if entity_ids is not None and cid not in entity_ids:
            continue
        for sid, se in list((ent.sources_state or {}).items()):
            if source_ids is not None and sid not in source_ids:
                continue
            se.next_run_at = _iso(clock)
            if clear_dead_letter:
                se.dead_letter = False
                se.dead_letter_reason = None
            if clear_circuit:
                se.circuit_breaker_state = "closed"
                se.circuit_open_until = None
            ent.sources_state[sid] = se
            n += 1
        queue[cid] = ent
    return n


def append_dlq_record(
    entry: SourceQueueEntry,
    *,
    meta_root: Path | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path | None:
    """Append dead-letter record for persistent failures."""
    if not entry.dead_letter:
        return None
    _, meta = ensure_roots(meta_root=meta_root)
    path = meta / DLQ_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "recorded_at": _now().isoformat(),
        "canonical_id": entry.canonical_id,
        "source_id": entry.source_id,
        "error_class": entry.error_class,
        "last_error": entry.last_error,
        "last_status": entry.last_status,
        "attempt_count": entry.attempt_count,
        "consecutive_failures": entry.consecutive_failures,
        "dead_letter_reason": entry.dead_letter_reason,
        "cursor": entry.cursor,
    }
    if extra:
        row.update(dict(extra))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def source_pair_metrics(
    queue: Mapping[str, EntityQueueEntry],
    entity_sources: Mapping[str, Sequence[str]],
    *,
    now: datetime | None = None,
    sla_hours: float = SLA_HOURS,
) -> dict[str, Any]:
    """Observability snapshot for entity×source queue health."""
    clock = now or _now()
    total = 0
    overdue = 0
    never = 0
    dlq = 0
    open_cb = 0
    by_class: dict[str, int] = {}
    lags: list[float] = []
    for cid, sources in entity_sources.items():
        ent = queue.get(cid) or EntityQueueEntry(canonical_id=cid)
        for sid in sources:
            total += 1
            se = (ent.sources_state or {}).get(sid) or SourceQueueEntry(canonical_id=cid, source_id=sid)
            if se.dead_letter:
                dlq += 1
            if se.is_circuit_open(clock):
                open_cb += 1
            if se.is_overdue(sla_hours=sla_hours, now=clock):
                overdue += 1
            lag = se.lag_hours(clock)
            if lag is None:
                never += 1
            else:
                lags.append(float(lag))
            cls = se.error_class or ErrorClass.NONE.value
            by_class[cls] = by_class.get(cls, 0) + 1
    lags_sorted = sorted(lags)

    def _pct(p: float) -> float | None:
        if not lags_sorted:
            return None
        idx = min(len(lags_sorted) - 1, max(0, int(round((p / 100.0) * (len(lags_sorted) - 1)))))
        return round(lags_sorted[idx], 3)

    return {
        "entity_count": len(entity_sources),
        "pair_count": total,
        "overdue_pairs": overdue,
        "never_succeeded_pairs": never,
        "dead_letter_count": dlq,
        "circuit_open_count": open_cb,
        "error_class_counts": by_class,
        "lag_hours_p50": _pct(50),
        "lag_hours_p95": _pct(95),
        "lag_hours_max": round(max(lags_sorted), 3) if lags_sorted else None,
        "sla_hours": sla_hours,
        "generated_at": clock.isoformat(),
    }


def backpressure_allows(
    *,
    cpu_percent: float | None = None,
    memory_percent: float | None = None,
    disk_percent: float | None = None,
    cpu_limit: float = 90.0,
    memory_limit: float = 90.0,
    disk_limit: float = 92.0,
    active_workers: int = 0,
    max_concurrency: int = 4,
) -> tuple[bool, str]:
    """Return (allowed, reason) for admitting another concurrent source job."""
    if active_workers >= max_concurrency:
        return False, "concurrency_cap"
    if cpu_percent is not None and cpu_percent >= cpu_limit:
        return False, "cpu_backpressure"
    if memory_percent is not None and memory_percent >= memory_limit:
        return False, "memory_backpressure"
    if disk_percent is not None and disk_percent >= disk_limit:
        return False, "disk_backpressure"
    return True, "ok"


def simulate_fair_rotation(
    entity_sources: Mapping[str, Sequence[str]],
    *,
    batch_size: int,
    cycles: int | None = None,
    sla_hours: float = SLA_HOURS,
    rng_seed: int = 42,
) -> dict[str, Any]:
    """Pure simulation: prove full rotation when universe > batch limit.

    Each cycle selects ``batch_size`` pairs by lag, marks them successful, and
    continues until every pair has been selected at least once (or cycles cap).
    """
    rng = random.Random(rng_seed)  # noqa: S311 — deterministic schedule sim, not crypto
    queue: dict[str, EntityQueueEntry] = {}
    ensure_entity_source_pairs(queue, entity_sources)
    pairs = list_source_pairs(queue, entity_sources)
    total = len(pairs)
    if total == 0:
        return {"pair_count": 0, "cycles": 0, "coverage": 1.0, "seen": []}
    seen: set[tuple[str, str]] = set()
    cycle = 0
    max_cycles = cycles if cycles is not None else (total // max(1, batch_size) + total + 5)
    clock = datetime(2026, 8, 1, tzinfo=UTC)
    selection_log: list[list[str]] = []
    while len(seen) < total and cycle < max_cycles:
        cycle += 1
        # advance clock so successful pairs age and lag ordering rotates
        clock = clock + timedelta(minutes=5)
        batch = select_source_pairs_by_lag(queue, entity_sources, limit=batch_size, now=clock, sla_hours=sla_hours)
        keys = [f"{se.canonical_id}|{se.source_id}" for se in batch]
        selection_log.append(keys)
        for se in batch:
            seen.add((se.canonical_id, se.source_id))
            ent = queue[se.canonical_id]
            apply_source_attempt_result(
                se,
                status=DocumentRunStatus.SUCCESS_ZERO.value,
                attempted_at=clock,
                sla_hours=sla_hours,
                scope_complete=True,
                documents_found=0,
                rng=rng,
            )
            ent.sources_state[se.source_id] = se
            queue[se.canonical_id] = ent
    return {
        "pair_count": total,
        "batch_size": batch_size,
        "cycles": cycle,
        "unique_seen": len(seen),
        "coverage": round(len(seen) / total, 6) if total else 1.0,
        "full_rotation": len(seen) == total,
        "selection_log_head": selection_log[:5],
        "selection_log_tail": selection_log[-3:],
    }


# re-export helpers used by tests / ops
__all__ = [
    "SLA_HOURS",
    "SourceQueueEntry",
    "EntityQueueEntry",
    "ErrorClass",
    "apply_attempt_result",
    "apply_multi_source_attempt",
    "apply_source_attempt_result",
    "append_dlq_record",
    "backpressure_allows",
    "build_sla_alerts",
    "compute_backoff_hours",
    "drain_decision",
    "ensure_entries",
    "ensure_entity_source_pairs",
    "get_source_entry",
    "is_retryable",
    "list_source_pairs",
    "load_entity_queue",
    "max_source_lag_hours",
    "queue_path",
    "queue_summary",
    "reprocess_selection",
    "save_entity_queue",
    "select_batch_by_source_lag",
    "select_batch_by_success_lag",
    "select_source_pairs_by_lag",
    "simulate_fair_rotation",
    "source_key",
    "source_pair_metrics",
    "overdue_entities",
]
