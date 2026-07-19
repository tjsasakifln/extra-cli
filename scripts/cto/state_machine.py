"""Persistent state machine with process lock for CTO Autopilot."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.ledger import append_ledger
from scripts.cto.paths import current_dir, lock_path, state_path
from scripts.cto.redaction import redact_obj

STATES = frozenset(
    {
        "IDLE",
        "OBSERVING",
        "DECIDING",
        "WAITING_HUMAN",
        "PREPARING",
        "EXECUTING",
        "VERIFYING",
        "REVIEWING",
        "REPAIRING",
        "ACCEPTED",
        "BLOCKED",
        "FAILED",
        "PAUSED",
        "DONE",
    }
)

# Allowed transitions (from -> set of to)
TRANSITIONS: dict[str, set[str]] = {
    "IDLE": {"OBSERVING", "PAUSED", "DONE"},
    "OBSERVING": {"DECIDING", "BLOCKED", "FAILED", "PAUSED"},
    "DECIDING": {
        "PREPARING",
        "WAITING_HUMAN",
        "BLOCKED",
        "FAILED",
        "PAUSED",
        "DONE",
        "IDLE",
    },
    "WAITING_HUMAN": {"IDLE", "PREPARING", "PAUSED", "DONE", "BLOCKED"},
    "PREPARING": {"EXECUTING", "FAILED", "PAUSED", "BLOCKED"},
    "EXECUTING": {"VERIFYING", "FAILED", "PAUSED", "REPAIRING"},
    "VERIFYING": {"REVIEWING", "FAILED", "PAUSED"},
    "REVIEWING": {
        "ACCEPTED",
        "REPAIRING",
        "BLOCKED",
        "WAITING_HUMAN",
        "FAILED",
        "DONE",
        "IDLE",
    },
    "REPAIRING": {"EXECUTING", "BLOCKED", "WAITING_HUMAN", "FAILED", "PAUSED"},
    "ACCEPTED": {"DONE", "IDLE", "OBSERVING"},
    "BLOCKED": {"IDLE", "WAITING_HUMAN", "PAUSED", "DONE", "OBSERVING"},
    "FAILED": {"IDLE", "PAUSED", "DONE", "OBSERVING"},
    "PAUSED": {"IDLE", "OBSERVING", "DONE"},
    "DONE": {"IDLE", "OBSERVING", "PAUSED"},
}

STALE_LOCK_SECONDS = 6 * 3600  # 6h


class StateError(RuntimeError):
    pass


class LockError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CTOState:
    status: str = "IDLE"
    cycle_id: str | None = None
    decision_id: str | None = None
    work_id: str | None = None
    issue_number: int | None = None
    repair_attempt: int = 0
    max_repair_attempts: int = 2
    last_error: str | None = None
    updated_at: str = field(default_factory=_utc_now)
    history: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_obj(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CTOState:
        return cls(
            status=str(data.get("status") or "IDLE"),
            cycle_id=data.get("cycle_id"),
            decision_id=data.get("decision_id"),
            work_id=data.get("work_id"),
            issue_number=data.get("issue_number"),
            repair_attempt=int(data.get("repair_attempt") or 0),
            max_repair_attempts=int(data.get("max_repair_attempts") or 2),
            last_error=data.get("last_error"),
            updated_at=str(data.get("updated_at") or _utc_now()),
            history=list(data.get("history") or []),
            meta=dict(data.get("meta") or {}),
        )


class ProcessLock:
    def __init__(self, root: Path | None = None, stale_seconds: int = STALE_LOCK_SECONDS):
        self.path = lock_path(root)
        self.stale_seconds = stale_seconds
        self.root = root

    def _read(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def acquire(self, owner: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._read()
        if existing:
            pid = existing.get("pid")
            ts = float(existing.get("ts") or 0)
            age = time.time() - ts
            alive = False
            if isinstance(pid, int) and pid > 0:
                try:
                    os.kill(pid, 0)
                    alive = True
                except OSError:
                    alive = False
            if alive and age < self.stale_seconds:
                raise LockError(
                    f"lock held by pid={pid} owner={existing.get('owner')} age={int(age)}s"
                )
            # stale — remove
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                raise LockError(f"cannot clear stale lock: {exc}") from exc
        payload = {
            "pid": os.getpid(),
            "owner": owner,
            "ts": time.time(),
            "acquired_at": _utc_now(),
        }
        tmp = self.path.with_suffix(".lock.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def release(self) -> None:
        existing = self._read()
        if not existing:
            return
        if existing.get("pid") not in (None, os.getpid()):
            # only owner pid releases
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def status(self) -> dict[str, Any]:
        data = self._read()
        if not data:
            return {"held": False}
        age = time.time() - float(data.get("ts") or 0)
        return {"held": True, "age_seconds": int(age), **data}


class StateMachine:
    def __init__(self, root: Path | None = None):
        self.root = root
        self.path = state_path(root)
        self.lock = ProcessLock(root)

    def load(self) -> CTOState:
        if not self.path.is_file():
            return CTOState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return CTOState.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return CTOState(status="FAILED", last_error="corrupt state.json")

    def save(self, state: CTOState) -> None:
        current_dir(self.root).mkdir(parents=True, exist_ok=True)
        state.updated_at = _utc_now()
        self.path.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def transition(
        self,
        to_status: str,
        *,
        reason: str,
        cycle_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CTOState:
        if to_status not in STATES:
            raise StateError(f"unknown state {to_status}")
        state = self.load()
        from_status = state.status
        allowed = TRANSITIONS.get(from_status, set())
        if to_status not in allowed and from_status != to_status:
            raise StateError(f"illegal transition {from_status} -> {to_status}")
        state.status = to_status
        if cycle_id:
            state.cycle_id = cycle_id
        if extra:
            if "decision_id" in extra:
                state.decision_id = extra["decision_id"]
            if "work_id" in extra:
                state.work_id = extra["work_id"]
            if "issue_number" in extra:
                state.issue_number = extra["issue_number"]
            if "repair_attempt" in extra:
                state.repair_attempt = int(extra["repair_attempt"])
            if "last_error" in extra:
                state.last_error = extra["last_error"]
            state.meta.update({k: v for k, v in extra.items() if k.startswith("meta_")})
        entry = {
            "from": from_status,
            "to": to_status,
            "reason": reason,
            "ts": _utc_now(),
        }
        state.history.append(entry)
        # keep history bounded
        state.history = state.history[-100:]
        self.save(state)
        append_ledger(
            "state_transition",
            entry,
            root=self.root,
            cycle_id=state.cycle_id,
        )
        return state

    def resume_target(self) -> str:
        """Where to resume after crash based on last state."""
        state = self.load()
        mapping = {
            "OBSERVING": "OBSERVING",
            "DECIDING": "DECIDING",
            "PREPARING": "PREPARING",
            "EXECUTING": "EXECUTING",
            "VERIFYING": "VERIFYING",
            "REVIEWING": "REVIEWING",
            "REPAIRING": "REPAIRING",
            "WAITING_HUMAN": "WAITING_HUMAN",
            "PAUSED": "PAUSED",
            "BLOCKED": "BLOCKED",
            "FAILED": "IDLE",
            "ACCEPTED": "DONE",
            "DONE": "IDLE",
            "IDLE": "IDLE",
        }
        return mapping.get(state.status, "IDLE")
