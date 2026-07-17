#!/usr/bin/env python3
"""File-based exclusive lock for long crawls (local / systemd friendly).

Prevents concurrent runs from sharing the same checkpoint directory.
Not a distributed lock — sufficient for single-host timers.
"""

from __future__ import annotations

import atexit
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class RunLock:
    path: Path
    run_id: str
    acquired: bool = False

    def acquire(self, *, stale_seconds: int = 6 * 3600) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                meta = json.loads(self.path.read_text(encoding="utf-8"))
                age = time.time() - float(meta.get("pid_started_at_unix") or 0)
                pid = int(meta.get("pid") or 0)
                if pid and _pid_alive(pid) and age < stale_seconds:
                    return False
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass
        payload = {
            "run_id": self.run_id,
            "pid": os.getpid(),
            "pid_started_at_unix": time.time(),
            "acquired_at": datetime.now(UTC).isoformat(),
            "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        self.acquired = True
        atexit.register(self.release)
        return True

    def heartbeat(self, extra: dict[str, Any] | None = None) -> None:
        if not self.acquired or not self.path.exists():
            return
        try:
            meta = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {"run_id": self.run_id, "pid": os.getpid()}
        meta["heartbeat_at"] = datetime.now(UTC).isoformat()
        if extra:
            meta["extra"] = extra
        self.path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            if self.path.exists():
                meta = json.loads(self.path.read_text(encoding="utf-8"))
                if str(meta.get("run_id")) == self.run_id:
                    self.path.unlink(missing_ok=True)
        except OSError:
            pass
        self.acquired = False


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
