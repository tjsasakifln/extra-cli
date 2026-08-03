"""Exclusive lock for entity×source queue drain (single-host, systemd-safe).

Prevents incompatible concurrent drains sharing the same meta_root checkpoint.
Not a multi-host distributed lock — sufficient for one VPS + timers.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class QueueDrainLock:
    path: Path
    run_id: str
    acquired: bool = False

    def acquire(self, *, stale_seconds: int = 6 * 3600) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                meta = json.loads(self.path.read_text(encoding="utf-8"))
                age = time.time() - float(meta.get("acquired_at_unix") or 0)
                pid = int(meta.get("pid") or 0)
                if pid and _pid_alive(pid) and age < stale_seconds:
                    return False
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass
        payload = {
            "run_id": self.run_id,
            "pid": os.getpid(),
            "acquired_at_unix": time.time(),
            "acquired_at": _now_iso(),
            "hostname": os.uname().nodename if hasattr(os, "uname") else None,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            if self.path.exists():
                meta = json.loads(self.path.read_text(encoding="utf-8"))
                if int(meta.get("pid") or 0) == os.getpid() and meta.get("run_id") == self.run_id:
                    self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass
        self.acquired = False

    def __enter__(self) -> QueueDrainLock:
        if not self.acquire():
            raise RuntimeError(f"queue drain lock held: {self.path}")
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def lock_path_for_meta(meta_root: Path) -> Path:
    return Path(meta_root) / "locks" / "entity_queue_drain.lock"


def lock_info(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
