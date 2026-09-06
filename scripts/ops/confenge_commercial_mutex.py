#!/usr/bin/env python3
"""Canonical single-host authority for CONFENGE commercial mutations.

The kernel ``flock`` is the atomic exclusion primitive.  The adjacent durable
JSON record is intentionally *not* deleted on release: it makes ownership,
completed-stage replay and crash recovery observable.  An ACTIVE record whose
kernel lock was released by a crash is never taken over implicitly.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import sys
import tempfile
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

EXIT_AUTHORITY_BUSY = 75
DEFAULT_AUTHORITY_ROOT = Path("/var/lib/extra-consultoria/commercial-cycle-authority")
CYCLE_STAGES = ("refresh", "reconcile", "contact", "feed")
VALID_STAGES = (*CYCLE_STAGES, "probe")


class AuthorityError(RuntimeError):
    """Base error raised before a protected mutation is entered."""


class AuthorityBusyError(AuthorityError):
    """Another or unrecovered execution owns the commercial boundary."""


class StageAlreadyCompletedError(AuthorityError):
    """A retry was deduplicated before reaching its mutation."""


class OperationAbortedError(AuthorityError):
    """An aborted operation cannot be reused."""


class AuthoritySequenceError(AuthorityError):
    """A cycle stage was requested out of order."""


@dataclass(frozen=True)
class AuthorityPaths:
    root: Path

    @property
    def lock(self) -> Path:
        return self.root / "authority.lock"

    @property
    def state(self) -> Path:
        return self.root / "authority.json"


def default_paths() -> AuthorityPaths:
    # Deliberately not configurable through environment: production entrypoints
    # must not be able to select disjoint lock domains. Tests inject
    # ``AuthorityPaths`` directly; the diagnostic CLI has an explicit --root.
    return AuthorityPaths(DEFAULT_AUTHORITY_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _process_start_ticks(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        tail = raw[raw.rfind(")") + 2 :].split()
        return tail[19]
    except (OSError, IndexError):
        return "unknown"


def _owner(owner_id: str) -> dict[str, Any]:
    pid = os.getpid()
    return {
        "id": owner_id,
        "host": socket.gethostname(),
        "pid": pid,
        "boot_id": _boot_id(),
        "process_start_ticks": _process_start_ticks(pid),
    }


def _operation_tombstone(record: dict[str, Any]) -> dict[str, Any]:
    """Retain enough terminal state to reject an old operation forever."""
    tombstone = {
        key: record.get(key)
        for key in (
            "operation_id",
            "operation_owner_id",
            "scope",
            "status",
            "created_at",
            "completed_at",
            "aborted_at",
            "abort_reason",
        )
        if record.get(key) is not None
    }
    tombstone["stages"] = {
        str(stage): {
            key: detail.get(key)
            for key in ("status", "completed_at", "aborted_at")
            if detail.get(key) is not None
        }
        for stage, detail in (record.get("stages") or {}).items()
        if isinstance(detail, dict)
    }
    return tombstone


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        tmp.unlink(missing_ok=True)


def _read_record(paths: AuthorityPaths) -> dict[str, Any] | None:
    if not paths.state.exists():
        return None
    try:
        value = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorityBusyError(f"invalid authority state; manual diagnosis required: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_id") != "confenge.commercial.authority.v1":
        raise AuthorityBusyError("invalid authority state; manual diagnosis required")
    if not str(value.get("operation_id") or "").strip():
        raise AuthorityBusyError("authority state has no operation id; manual diagnosis required")
    return value


def _open_locked(paths: AuthorityPaths) -> TextIO:
    paths.root.mkdir(mode=0o750, parents=True, exist_ok=True)
    handle = paths.lock.open("a+", encoding="utf-8")
    os.chmod(paths.lock, 0o600)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise AuthorityBusyError("commercial authority lock is active") from exc
    return handle


def _owner_is_live(owner: dict[str, Any]) -> bool | None:
    if owner.get("host") != socket.gethostname():
        return None
    recorded_boot = str(owner.get("boot_id") or "")
    if recorded_boot and recorded_boot != "unknown" and recorded_boot != _boot_id():
        return False
    try:
        pid = int(owner.get("pid") or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    current_start = _process_start_ticks(pid)
    if current_start == "unknown":
        return False
    recorded_start = str(owner.get("process_start_ticks") or "")
    if not recorded_start or recorded_start == "unknown":
        return None
    return current_start == recorded_start


class StageClaim(AbstractContextManager["StageClaim"]):
    def __init__(
        self,
        *,
        paths: AuthorityPaths,
        handle: TextIO,
        record: dict[str, Any],
    ) -> None:
        self.paths = paths
        self.handle = handle
        self.record = record
        self.completed = False
        self._prior_operation_id = os.environ.get("CONFENGE_COMMERCIAL_OPERATION_ID")
        self._prior_scope = os.environ.get("CONFENGE_COMMERCIAL_OPERATION_SCOPE")
        os.environ["CONFENGE_COMMERCIAL_OPERATION_ID"] = str(record["operation_id"])
        os.environ["CONFENGE_COMMERCIAL_OPERATION_SCOPE"] = str(record["scope"])

    @property
    def operation_id(self) -> str:
        return str(self.record["operation_id"])

    def complete(self, result: dict[str, Any] | None = None) -> None:
        if self.completed:
            return
        at = _now()
        stage = str(self.record["active_stage"])
        stages = dict(self.record.get("stages") or {})
        stages[stage] = {
            **dict(stages.get(stage) or {}),
            "status": "COMPLETED",
            "completed_at": at,
            "result": result or {},
        }
        terminal = self.record.get("scope") == "stage" or stage == "feed"
        self.record = {
            **self.record,
            "status": "COMPLETED" if terminal else "OPEN",
            "active_stage": None,
            "owner": None,
            "updated_at": at,
            "completed_at": at if terminal else None,
            "stages": stages,
        }
        _atomic_json(self.paths.state, self.record)
        self.completed = True

    def abort(self, reason: str) -> None:
        if self.completed:
            return
        at = _now()
        stage = str(self.record["active_stage"])
        stages = dict(self.record.get("stages") or {})
        stages[stage] = {
            **dict(stages.get(stage) or {}),
            "status": "ABORTED",
            "aborted_at": at,
            "reason": reason,
        }
        self.record = {
            **self.record,
            "status": "ABORTED",
            "active_stage": None,
            "owner": None,
            "updated_at": at,
            "aborted_at": at,
            "abort_reason": reason,
            "stages": stages,
        }
        _atomic_json(self.paths.state, self.record)
        self.completed = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if not self.completed:
                self.abort(f"{type(exc).__name__}: {exc}" if exc is not None else "stage exited without completion")
        finally:
            if self._prior_operation_id is None:
                os.environ.pop("CONFENGE_COMMERCIAL_OPERATION_ID", None)
            else:
                os.environ["CONFENGE_COMMERCIAL_OPERATION_ID"] = self._prior_operation_id
            if self._prior_scope is None:
                os.environ.pop("CONFENGE_COMMERCIAL_OPERATION_SCOPE", None)
            else:
                os.environ["CONFENGE_COMMERCIAL_OPERATION_SCOPE"] = self._prior_scope
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def acquire_stage(
    *,
    paths: AuthorityPaths | None = None,
    operation_id: str,
    stage: str,
    scope: str,
    owner_id: str,
) -> StageClaim:
    paths = paths or default_paths()
    operation_id = operation_id.strip()
    owner_id = owner_id.strip()
    if not operation_id or not owner_id:
        raise AuthorityError("operation_id and owner_id are required")
    if stage not in VALID_STAGES or scope not in {"stage", "cycle"}:
        raise AuthorityError("invalid commercial authority stage or scope")
    if scope == "cycle" and stage not in CYCLE_STAGES:
        raise AuthorityError("cycle scope requires a canonical cycle stage")
    handle = _open_locked(paths)
    try:
        previous = _read_record(paths)
        stages: dict[str, Any] = {}
        history: dict[str, Any] = {}
        created_at = _now()
        operation_owner_id = owner_id
        if previous:
            previous_status = str(previous.get("status") or "")
            if previous_status not in {"ACTIVE", "OPEN", "COMPLETED", "ABORTED"}:
                raise AuthorityBusyError(f"unknown authority status {previous_status!r}; manual diagnosis required")
            raw_history = previous.get("history") or {}
            if not isinstance(raw_history, dict):
                raise AuthorityBusyError("invalid authority history; manual diagnosis required")
            history = dict(raw_history)
            same_operation = previous.get("operation_id") == operation_id
            historic = history.get(operation_id)
            if historic:
                historic_status = str(historic.get("status") or "") if isinstance(historic, dict) else ""
                if historic_status == "ABORTED":
                    raise OperationAbortedError(f"operation {operation_id} is ABORTED")
                if historic_status == "COMPLETED":
                    raise StageAlreadyCompletedError(f"operation {operation_id} already completed")
                raise AuthorityBusyError("invalid historic authority state; manual diagnosis required")
            if previous_status == "ACTIVE":
                raise AuthorityBusyError("unrecovered ACTIVE authority; explicit recovery is required")
            if same_operation and previous_status == "ABORTED":
                raise OperationAbortedError(f"operation {operation_id} is ABORTED")
            if same_operation and stage in (previous.get("stages") or {}):
                if previous["stages"][stage].get("status") == "COMPLETED":
                    raise StageAlreadyCompletedError(f"operation {operation_id} stage {stage} already completed")
            if previous_status == "OPEN":
                if not same_operation:
                    raise AuthorityBusyError(f"commercial cycle reserved by {previous.get('operation_id')}")
                if previous.get("scope") != "cycle":
                    raise AuthorityBusyError("invalid OPEN stage-scoped authority")
                if scope != "cycle":
                    raise AuthorityBusyError("an OPEN cycle cannot be continued with stage scope")
                operation_owner_id = str(previous.get("operation_owner_id") or "")
                if operation_owner_id != owner_id:
                    raise AuthorityBusyError(f"commercial cycle reserved by owner {operation_owner_id}")
                stages = dict(previous.get("stages") or {})
                completed = [(stages.get(name) or {}).get("status") == "COMPLETED" for name in CYCLE_STAGES]
                if any(completed[index] and not all(completed[:index]) for index in range(len(completed))):
                    raise AuthorityBusyError("non-contiguous completed stages; manual diagnosis required")
                completed_count = sum(completed)
                expected = CYCLE_STAGES[completed_count] if completed_count < len(CYCLE_STAGES) else None
                if stage != expected:
                    raise AuthoritySequenceError(f"expected stage {expected}, got {stage}")
                created_at = str(previous.get("created_at") or created_at)
            elif same_operation and previous_status == "COMPLETED":
                raise StageAlreadyCompletedError(f"operation {operation_id} already completed")
            elif not same_operation:
                history[str(previous["operation_id"])] = _operation_tombstone(previous)

        at = _now()
        stages[stage] = {"status": "ACTIVE", "started_at": at}
        record = {
            "schema_id": "confenge.commercial.authority.v1",
            "operation_id": operation_id,
            "operation_owner_id": operation_owner_id,
            "scope": scope,
            "status": "ACTIVE",
            "active_stage": stage,
            "created_at": created_at,
            "acquired_at": at,
            "updated_at": at,
            "owner": _owner(owner_id),
            "stages": stages,
            "history": history,
        }
        _atomic_json(paths.state, record)
        return StageClaim(paths=paths, handle=handle, record=record)
    except Exception:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        raise


def acquire_stage_from_env(
    stage: str,
    *,
    operation_id: str | None = None,
    scope: str | None = None,
    owner_id: str | None = None,
) -> StageClaim:
    resolved_operation = operation_id or os.getenv("CONFENGE_COMMERCIAL_OPERATION_ID") or os.getenv("INVOCATION_ID")
    if not resolved_operation:
        raise AuthorityError("commercial operation id is required before mutation")
    resolved_scope = scope or os.getenv("CONFENGE_COMMERCIAL_OPERATION_SCOPE", "stage")
    resolved_owner = (
        owner_id or os.getenv("CONFENGE_COMMERCIAL_OWNER_ID") or f"uid:{os.getuid()}@{socket.gethostname()}"
    )
    return acquire_stage(
        operation_id=resolved_operation,
        stage=stage,
        scope=resolved_scope,
        owner_id=resolved_owner,
    )


def assert_inherited_authority(stage: str, paths: AuthorityPaths | None = None) -> dict[str, Any]:
    """Verify that this process descends from the process holding ``stage``.

    This is used by contact-cycle child CLIs.  Merely copying an operation id is
    insufficient: the durable record must be ACTIVE, the kernel lock must be
    held, and the recorded owner PID must be an ancestor of the caller.
    """
    paths = paths or default_paths()
    operation_id = os.getenv("CONFENGE_COMMERCIAL_OPERATION_ID") or os.getenv("INVOCATION_ID")
    if not operation_id:
        raise AuthorityError("inherited commercial operation id is missing")
    status = inspect_authority(paths)
    record = status.get("record") or {}
    if (
        status.get("status") != "ACTIVE"
        or status.get("kernel_lock_held") is not True
        or record.get("operation_id") != operation_id
        or record.get("active_stage") != stage
    ):
        raise AuthorityError("no matching active commercial authority")
    try:
        owner_pid = int((record.get("owner") or {}).get("pid") or 0)
    except (TypeError, ValueError):
        owner_pid = 0
    pid = os.getpid()
    while pid > 1 and pid != owner_pid:
        try:
            status_line = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
            ppid_line = next(line for line in status_line.splitlines() if line.startswith("PPid:"))
            pid = int(ppid_line.split(":", 1)[1].strip())
        except (OSError, StopIteration, ValueError):
            pid = 0
            break
    if pid != owner_pid:
        raise AuthorityError("commercial authority owner is not an ancestor of this process")
    return record


def inspect_authority(paths: AuthorityPaths | None = None) -> dict[str, Any]:
    paths = paths or default_paths()
    try:
        record = _read_record(paths)
    except AuthorityBusyError as exc:
        return {"ok": False, "status": "INVALID", "error": str(exc), "state_path": str(paths.state)}
    if record is None:
        return {"ok": True, "status": "EMPTY", "record": None, "state_path": str(paths.state)}
    try:
        handle = _open_locked(paths)
    except AuthorityBusyError:
        locked = True
    else:
        locked = False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
    status = str(record.get("status") or "UNKNOWN")
    if status == "ACTIVE" and not locked:
        live = _owner_is_live(dict(record.get("owner") or {}))
        status = "STALE_CANDIDATE" if live is False else "ACTIVE_OWNER_UNSAFE_TO_RECOVER"
    return {
        "ok": status not in {"INVALID", "UNKNOWN"},
        "status": status,
        "kernel_lock_held": locked,
        "record": record,
        "state_path": str(paths.state),
        "lock_path": str(paths.lock),
    }


def recover_stale_authority(
    paths: AuthorityPaths | None = None,
    *,
    expected_operation_id: str,
    recovered_by: str,
) -> dict[str, Any]:
    paths = paths or default_paths()
    handle = _open_locked(paths)
    try:
        record = _read_record(paths)
        if not record or record.get("operation_id") != expected_operation_id:
            raise AuthorityError("authority operation id changed; recovery refused")
        if record.get("status") != "ACTIVE":
            raise AuthorityError("only a crashed ACTIVE authority can be recovered as stale")
        live = _owner_is_live(dict(record.get("owner") or {}))
        if live is not False:
            raise AuthorityBusyError("recorded owner may still be live; recovery refused")
        at = _now()
        active_stage = str(record.get("active_stage") or "unknown")
        stages = dict(record.get("stages") or {})
        stages[active_stage] = {
            **dict(stages.get(active_stage) or {}),
            "status": "ABORTED",
            "aborted_at": at,
            "reason": "STALE_OWNER_CONFIRMED_DEAD",
        }
        record.update(
            status="ABORTED",
            active_stage=None,
            owner=None,
            aborted_at=at,
            updated_at=at,
            abort_reason="STALE_OWNER_CONFIRMED_DEAD",
            recovered_by=recovered_by,
            stages=stages,
        )
        _atomic_json(paths.state, record)
        return record
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def abort_open_authority(
    paths: AuthorityPaths | None = None,
    *,
    expected_operation_id: str,
    aborted_by: str,
    reason: str,
) -> dict[str, Any]:
    """Explicitly abandon a cycle reserved between stages.

    ACTIVE ownership is protected by the kernel lock and is never handled here;
    crashed ACTIVE ownership must go through ``recover_stale_authority``.
    """
    paths = paths or default_paths()
    handle = _open_locked(paths)
    try:
        record = _read_record(paths)
        if not record or record.get("operation_id") != expected_operation_id:
            raise AuthorityError("authority operation id changed; abort refused")
        if record.get("status") != "OPEN":
            raise AuthorityError("only an OPEN between-stage authority can be aborted")
        at = _now()
        record.update(
            status="ABORTED",
            active_stage=None,
            owner=None,
            aborted_at=at,
            updated_at=at,
            abort_reason=reason,
            aborted_by=aborted_by,
        )
        _atomic_json(paths.state, record)
        return record
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_paths().root)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    recover = sub.add_parser("recover-stale")
    recover.add_argument("--expected-operation-id", required=True)
    recover.add_argument("--recovered-by", required=True)
    abort_open = sub.add_parser("abort-open")
    abort_open.add_argument("--expected-operation-id", required=True)
    abort_open.add_argument("--aborted-by", required=True)
    abort_open.add_argument("--reason", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--operation-id", required=True)
    probe.add_argument("--owner-id", required=True)
    probe.add_argument("--hold-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    paths = AuthorityPaths(args.root)
    try:
        if args.command == "status":
            payload = inspect_authority(paths)
        elif args.command == "recover-stale":
            payload = recover_stale_authority(
                paths,
                expected_operation_id=args.expected_operation_id,
                recovered_by=args.recovered_by,
            )
        elif args.command == "abort-open":
            payload = abort_open_authority(
                paths,
                expected_operation_id=args.expected_operation_id,
                aborted_by=args.aborted_by,
                reason=args.reason,
            )
        else:
            with acquire_stage(
                paths=paths,
                operation_id=args.operation_id,
                stage="probe",
                scope="stage",
                owner_id=args.owner_id,
            ) as claim:
                time.sleep(max(0, args.hold_seconds))
                claim.complete({"probe": True})
            payload = inspect_authority(paths)
    except AuthorityError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return EXIT_AUTHORITY_BUSY
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
