"""Process lock to prevent concurrent registry mutations."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from scripts.company_registry.paths import ensure_layout, locks_dir


class RegistryLock:
    def __init__(self, name: str = "company_registry", *, timeout_s: float = 0):
        ensure_layout()
        self.path = locks_dir() / f"{name}.lock"
        self.timeout_s = timeout_s
        self._fh: Any = None

    def acquire(self) -> bool:
        start = time.time()
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                self._fh = os.fdopen(fd, "w")
                self._fh.write(f"pid={os.getpid()}\n")
                self._fh.flush()
                return True
            except FileExistsError:
                if self.timeout_s and (time.time() - start) < self.timeout_s:
                    time.sleep(0.2)
                    continue
                return False

    def release(self) -> None:
        try:
            if self._fh:
                self._fh.close()
                self._fh = None
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "RegistryLock":
        if not self.acquire():
            raise RuntimeError(f"registry_lock_busy:{self.path}")
        return self

    def __exit__(self, *args: object) -> None:
        self.release()
