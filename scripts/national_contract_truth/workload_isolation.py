"""#317 — isolate national ingest from reports and backup.

Admission control refuses a damaging overlap. Overload pauses with an
intact checkpoint and never returns false success. A concurrent VPS soak
that did not run keeps the seal UNPROVEN.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

SCHEMA_VERSION = "workload-isolation/1.0"
POLICY_VERSION = "vps-isolation-v1"

REQUIRED_SESSION = (
    "application_name",
    "statement_timeout",
    "lock_timeout",
    "idle_in_transaction_session_timeout",
)

PROTECTED_WINDOWS = frozenset({"backup", "maintenance", "pack_publish"})
INGEST_WORKLOADS = frozenset({"national_ingest", "pncp_contracts"})

Decision = Literal["ADMIT", "RESCHEDULE", "PAUSE", "REFUSE"]
Seal = Literal["PROVEN", "UNPROVEN"]


class IsolationError(ValueError):
    """Ingest cannot be admitted."""


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class SessionSettings:
    application_name: str
    statement_timeout_ms: int
    lock_timeout_ms: int
    idle_in_transaction_session_timeout_ms: int
    max_connections: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "application_name": self.application_name,
            "statement_timeout": self.statement_timeout_ms,
            "lock_timeout": self.lock_timeout_ms,
            "idle_in_transaction_session_timeout": self.idle_in_transaction_session_timeout_ms,
            "max_connections": self.max_connections,
        }


@dataclass(frozen=True)
class IsolationLimits:
    cpu_quota_percent: int
    memory_max_mb: int
    io_weight: int
    worker_limit: int
    slice: str


@dataclass(frozen=True)
class CalendarEvent:
    kind: str
    start: str
    end: str


@dataclass(frozen=True)
class HostPressure:
    disk_free_ratio: float
    cpu_util: float
    checkpoint_intact: bool
    last_approved_snapshot_readable: bool
    soak_ran: bool = False


_DECISION_RANK: dict[Decision, int] = {
    "ADMIT": 0,
    "RESCHEDULE": 1,
    "PAUSE": 2,
    "REFUSE": 3,
}
_MINUTES_PER_DAY = 24 * 60


def _clock_minutes(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise IsolationError(f"invalid_time:{value}")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise IsolationError(f"invalid_time:{value}") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise IsolationError(f"invalid_time:{value}")
    return hour * 60 + minute


def _segments(start: int, end: int) -> tuple[tuple[int, int], ...]:
    if end > start:
        return ((start, end),)
    if end == start:
        return ((0, _MINUTES_PER_DAY),)
    return ((start, _MINUTES_PER_DAY), (0, end))


def _overlaps(job_start: str, job_end: str, event: CalendarEvent) -> bool:
    job_segs = _segments(_clock_minutes(job_start), _clock_minutes(job_end))
    event_segs = _segments(_clock_minutes(event.start), _clock_minutes(event.end))
    for job_a, job_b in job_segs:
        for ev_a, ev_b in event_segs:
            if not (job_b <= ev_a or job_a >= ev_b):
                return True
    return False


def _escalate(current: Decision, incoming: Decision) -> Decision:
    if _DECISION_RANK[incoming] > _DECISION_RANK[current]:
        return incoming
    return current


def admit_ingest(
    *,
    workload: str,
    job_start: str,
    job_end: str,
    calendar: tuple[CalendarEvent, ...],
    session: SessionSettings,
    limits: IsolationLimits,
    pressure: HostPressure,
) -> dict[str, Any]:
    """Fail-closed admission. Overload pauses; overlap refuses; never false success."""
    blockers: list[str] = []
    decision: Decision = "ADMIT"
    if workload not in INGEST_WORKLOADS:
        blockers.append(f"unknown_workload:{workload}")
        decision = _escalate(decision, "REFUSE")
    missing = [name for name in REQUIRED_SESSION if not session.as_dict().get(name)]
    if missing:
        blockers.append(f"session_missing:{missing}")
        decision = _escalate(decision, "REFUSE")
    if session.max_connections < 1 or limits.worker_limit < 1:
        blockers.append("non_positive_limit")
        decision = _escalate(decision, "REFUSE")
    overlaps = [e.kind for e in calendar if e.kind in PROTECTED_WINDOWS and _overlaps(job_start, job_end, e)]
    if overlaps:
        blockers.append(f"calendar_overlap:{overlaps}")
        decision = _escalate(decision, "RESCHEDULE")
    if pressure.disk_free_ratio < 0.10:
        blockers.append("disk_pressure")
        decision = _escalate(decision, "PAUSE")
    if pressure.cpu_util > 0.90:
        blockers.append("cpu_pressure")
        decision = _escalate(decision, "PAUSE")
    if not pressure.checkpoint_intact:
        blockers.append("checkpoint_not_intact")
        decision = _escalate(decision, "REFUSE")
    if not pressure.last_approved_snapshot_readable:
        blockers.append("approved_snapshot_unreadable")
        decision = _escalate(decision, "REFUSE")

    false_success = decision in {"PAUSE", "REFUSE", "RESCHEDULE"}
    seal: Seal = "PROVEN" if pressure.soak_ran and not blockers else "UNPROVEN"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "workload": workload,
        "decision": decision,
        "success": decision == "ADMIT",
        "false_success": False,
        "checkpoint_intact": pressure.checkpoint_intact,
        "last_approved_snapshot_readable": pressure.last_approved_snapshot_readable,
        "session": session.as_dict(),
        "limits": {
            "slice": limits.slice,
            "cpu_quota_percent": limits.cpu_quota_percent,
            "memory_max_mb": limits.memory_max_mb,
            "io_weight": limits.io_weight,
            "worker_limit": limits.worker_limit,
        },
        "blockers": blockers,
        "soak_seal": seal,
        "claim_vps_isolated": seal == "PROVEN",
    }
    if false_success and payload["success"]:
        raise IsolationError("false_success_forbidden")
    payload["admission_hash"] = sha256_payload(payload)
    return payload
