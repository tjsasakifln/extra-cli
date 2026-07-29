"""Canonical exclusive lock for all PNCP contracts writers.

ONE_PRODUCTION_LOCK_DOMAIN — every path that upserts into
``pncp_supplier_contracts`` (or writes the incremental contracts checkpoint)
must acquire this lock.

Default path: ``/run/lock/extra-contracts-writer.lock``
Override: env ``EXTRA_CONTRACTS_WRITER_LOCK``

Exit code ``EXIT_LOCK_BUSY`` (75) when non-blocking acquire fails.
Lock busy is **not** a source failure — systemd units should list
``SuccessExitStatus=75``.
"""
from __future__ import annotations

import atexit
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import TextIO

logger = logging.getLogger(__name__)

# sysexits.h EX_TEMPFAIL
EXIT_LOCK_BUSY = 75

DEFAULT_LOCK_PATH = "/run/lock/extra-contracts-writer.lock"
# Fallback when /run/lock is not writable (dev / CI)
FALLBACK_LOCK_PATH = "/tmp/extra-contracts-writer.lock"  # noqa: S108


def lock_path() -> Path:
    raw = os.getenv("EXTRA_CONTRACTS_WRITER_LOCK") or DEFAULT_LOCK_PATH
    return Path(raw)


@dataclass
class ContractsWriterLock:
    """Context manager for exclusive contracts writer lock (fcntl flock)."""

    path: Path | None = None
    blocking: bool = False
    _fh: TextIO | None = None
    owned: bool = False
    owner_note: str = ""

    def __post_init__(self) -> None:
        if self.path is None:
            self.path = lock_path()

    def acquire(self) -> bool:
        """Try to acquire lock. Returns True on success, False if busy (nonblock)."""
        if self.path is None:
            self.path = lock_path()
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(path, "a+", encoding="utf-8")  # noqa: SIM115
        except OSError:
            # /run/lock may be root-only; fall back for local/tests
            if str(path) == DEFAULT_LOCK_PATH:
                path = Path(FALLBACK_LOCK_PATH)
                self.path = path
                path.parent.mkdir(parents=True, exist_ok=True)
                fh = open(path, "a+", encoding="utf-8")  # noqa: SIM115
            else:
                raise

        try:
            import fcntl

            flags = fcntl.LOCK_EX
            if not self.blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(fh.fileno(), flags)
        except BlockingIOError:
            fh.close()
            logger.warning(
                "contracts writer lock busy path=%s (not a source failure)",
                path,
            )
            return False
        except OSError as exc:
            fh.close()
            logger.error("contracts writer lock acquire failed: %s", exc)
            raise

        owner = f"pid={os.getpid()} note={self.owner_note}".strip()
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(owner + "\n")
            fh.flush()
        except OSError:
            pass

        self._fh = fh
        self.owned = True
        atexit.register(self.release)
        logger.info("contracts writer lock acquired path=%s %s", path, owner)
        return True

    def release(self) -> None:
        if not self.owned or self._fh is None:
            return
        try:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None
        self.owned = False

    def __enter__(self) -> ContractsWriterLock:
        if not self.acquire():
            raise ContractsLockBusyError(str(self.path))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


class ContractsLockBusyError(RuntimeError):
    """Raised when non-blocking acquire fails."""


def acquire_or_exit(
    *,
    blocking: bool = False,
    owner_note: str = "",
) -> ContractsWriterLock:
    """Acquire lock or exit process with EXIT_LOCK_BUSY."""
    lock = ContractsWriterLock(blocking=blocking, owner_note=owner_note)
    if not lock.acquire():
        print(
            f"LOCK_BUSY: contracts writer lock held ({lock.path}); "
            f"exit={EXIT_LOCK_BUSY}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_LOCK_BUSY)
    return lock
