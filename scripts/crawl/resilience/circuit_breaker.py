"""Persistent circuit breaker (filesystem), env-scoped and multi-process safe."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any  # noqa: I001


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


@dataclass
class CircuitBreakerState:
    environment: str
    source: str
    route: str
    consecutive_failures: int = 0
    opened_at: float | None = None
    cooldown_until: float | None = None
    last_failure: str | None = None
    last_http_status: int | None = None
    half_open_attempt: bool = False
    state: str = "closed"  # closed | open | half_open

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitBreakerState:
        return cls(
            environment=str(data.get("environment") or "development"),
            source=str(data.get("source") or "unknown"),
            route=str(data.get("route") or "default"),
            consecutive_failures=int(data.get("consecutive_failures") or 0),
            opened_at=data.get("opened_at"),
            cooldown_until=data.get("cooldown_until"),
            last_failure=data.get("last_failure"),
            last_http_status=data.get("last_http_status"),
            half_open_attempt=bool(data.get("half_open_attempt")),
            state=str(data.get("state") or "closed"),
        )


class PersistentCircuitBreaker:
    """File-backed breaker with exclusive lock for concurrent processes."""

    def __init__(
        self,
        root: Path,
        *,
        environment: str,
        source: str,
        route: str = "default",
        threshold: int = 5,
        cooldown_seconds: float = 300.0,
        clock: Any = time.time,
    ):
        self.root = root
        self.environment = environment
        self.source = source
        self.route = route
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.path = root / environment / source / f"{route}.json"
        self.lock_path = self.path.with_suffix(".lock")

    def _lock(self) -> Any:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+", encoding="utf-8")  # noqa: SIM115
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            # Best-effort on platforms without flock.
            pass
        return fh

    def _unlock(self, fh: Any) -> None:
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        fh.close()

    def load(self) -> CircuitBreakerState:
        if not self.path.is_file():
            return CircuitBreakerState(environment=self.environment, source=self.source, route=self.route)
        try:
            return CircuitBreakerState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return CircuitBreakerState(environment=self.environment, source=self.source, route=self.route)

    def _save(self, state: CircuitBreakerState) -> None:
        _atomic_json(self.path, state.to_dict())

    def allow_request(self) -> bool:
        fh = self._lock()
        try:
            state = self.load()
            now = float(self.clock())
            if state.state == "closed":
                return True
            if state.state == "open":
                cooldown = float(state.cooldown_until or 0)
                if now >= cooldown:
                    state.state = "half_open"
                    state.half_open_attempt = True
                    self._save(state)
                    return True
                return False
            if state.state == "half_open":
                # Only one probe at a time.
                return bool(state.half_open_attempt)
            return True
        finally:
            self._unlock(fh)

    def record_success(self) -> CircuitBreakerState:
        fh = self._lock()
        try:
            state = self.load()
            state.consecutive_failures = 0
            state.opened_at = None
            state.cooldown_until = None
            state.half_open_attempt = False
            state.state = "closed"
            state.last_failure = None
            self._save(state)
            return state
        finally:
            self._unlock(fh)

    def record_failure(self, *, http_status: int | None = None, error: str | None = None) -> CircuitBreakerState:
        fh = self._lock()
        try:
            state = self.load()
            now = float(self.clock())
            state.consecutive_failures = int(state.consecutive_failures) + 1
            state.last_failure = datetime.now(UTC).isoformat()
            state.last_http_status = http_status
            if state.state == "half_open" or state.consecutive_failures >= self.threshold:
                state.state = "open"
                state.opened_at = state.opened_at or now
                state.cooldown_until = now + self.cooldown_seconds
                state.half_open_attempt = False
                if error:
                    state.last_failure = f"{state.last_failure}|{error}"
            self._save(state)
            return state
        finally:
            self._unlock(fh)

    def snapshot(self) -> dict[str, Any]:
        return self.load().to_dict()
