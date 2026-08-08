"""Per-source rate limiting, retry with exponential backoff.

Used by batch enrichment when network adapters are enabled. Pure helpers —
no global state required; inject RateLimiter instances per source.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimiter:
    """Fixed-window rate limiter: max_calls per window_seconds."""

    max_calls: int = 30
    window_seconds: float = 60.0
    _timestamps: list[float] = field(default_factory=list)

    def allow(self, *, now: float | None = None) -> bool:
        t = now if now is not None else time.monotonic()
        cutoff = t - self.window_seconds
        self._timestamps = [x for x in self._timestamps if x > cutoff]
        if len(self._timestamps) >= self.max_calls:
            return False
        self._timestamps.append(t)
        return True

    def wait_if_needed(self, *, now: float | None = None, sleep_fn: Callable[[float], None] | None = None) -> float:
        """Block until a slot is available. Returns seconds slept."""
        sleep = sleep_fn or time.sleep
        waited = 0.0
        while not self.allow(now=now):
            delay = max(0.05, self.window_seconds / max(1, self.max_calls))
            sleep(delay)
            waited += delay
            now = None  # recompute wall
        return waited


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    jitter: float = 0.25
    retryable_exceptions: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError, OSError)

    def delay_for_attempt(self, attempt: int) -> float:
        """attempt is 0-based after a failure."""
        raw = min(self.max_delay_seconds, self.base_delay_seconds * (2**attempt))
        jitter_amt = raw * self.jitter * random.random()  # noqa: S311 — non-crypto jitter
        return raw + jitter_amt


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    rate_limiter: RateLimiter | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Execute fn with optional rate limit + exponential backoff retries."""
    pol = policy or RetryPolicy()
    sleep = sleep_fn or time.sleep
    last_exc: BaseException | None = None
    for attempt in range(pol.max_attempts):
        if rate_limiter is not None:
            rate_limiter.wait_if_needed(sleep_fn=sleep)
        try:
            return fn()
        except pol.retryable_exceptions as exc:
            last_exc = exc
            if attempt + 1 >= pol.max_attempts:
                break
            delay = pol.delay_for_attempt(attempt)
            if on_retry:
                on_retry(attempt, exc, delay)
            sleep(delay)
    if last_exc is None:
        raise RuntimeError("call_with_retry exhausted without exception")
    raise last_exc


# Default per-source budgets (calls per minute)
DEFAULT_SOURCE_LIMITS: dict[str, RateLimiter] = {
    "registry": RateLimiter(max_calls=60, window_seconds=60.0),
    "web_search": RateLimiter(max_calls=20, window_seconds=60.0),
    "site": RateLimiter(max_calls=40, window_seconds=60.0),
    "public_docs": RateLimiter(max_calls=60, window_seconds=60.0),
    "default": RateLimiter(max_calls=30, window_seconds=60.0),
}


def limiter_for(source: str, registry: dict[str, RateLimiter] | None = None) -> RateLimiter:
    reg = registry or DEFAULT_SOURCE_LIMITS
    return reg.get(source) or reg.get("default") or RateLimiter()


@dataclass
class RetryStats:
    attempts: int = 0
    retries: int = 0
    rate_limit_waits: int = 0
    last_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "retries": self.retries,
            "rate_limit_waits": self.rate_limit_waits,
            "last_error": self.last_error,
        }
