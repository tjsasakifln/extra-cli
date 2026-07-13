"""Rate limiter for PNCP API and other external sources.

Implements a token-bucket algorithm with configurable rate and period.
Async-compatible: both sync and async ``check()`` methods provided.
Minimum default: 1 call/sec.
"""

from __future__ import annotations

import asyncio
import time
from threading import Lock
from typing import Any


class TokenBucketRateLimiter:
    """Token-bucket rate limiter.

    Allows *rate* calls per *period* seconds.  The bucket starts full and
    refills at a constant rate.  ``check()`` returns True if a token is
    available (consuming it), or False for non-blocking usage.

    Thread-safe (uses ``threading.Lock``).
    Async-compatible (provides ``async_check()`` that sleeps until a token
    is available).

    Args:
        rate: Number of calls allowed per *period*.
        period: Time window in seconds.

    Example::

        limiter = TokenBucketRateLimiter(rate=2, period=1.0)

        # Non-blocking check
        if limiter.check():
            do_request()

        # Async wait
        await limiter.async_check()
        do_request()
    """

    def __init__(self, rate: float = 1.0, period: float = 1.0) -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        if period <= 0:
            raise ValueError("period must be > 0")

        self.rate = rate
        self.period = period
        self._tokens = rate
        self._max_tokens = rate
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self.rate / self.period)
        self._last_refill = now

    def check(self) -> bool:
        """Non-blocking token check.

        Returns:
            True if a token was consumed (call is allowed).
            False if no token is available (call should be delayed).
        """
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1.0
                return True
            return False

    async def async_check(self) -> None:
        """Async await until a token is available.

        Blocks (sleeps) until a token can be consumed, then returns.
        Uses asyncio.sleep to yield control to the event loop.
        """
        while True:
            if self.check():
                return
            await asyncio.sleep(self.period / max(self.rate, 1) * 0.1)

    async def __aenter__(self) -> TokenBucketRateLimiter:
        await self.async_check()
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


# Default instance for project-wide use
pncp_rate_limiter = TokenBucketRateLimiter(rate=1.0, period=1.0)


__all__ = [
    "TokenBucketRateLimiter",
    "pncp_rate_limiter",
]
