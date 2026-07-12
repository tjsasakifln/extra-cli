"""STUB: Rate limiter for PNCP API.

Minimal definitions to enable imports from rate_limiter.
Full implementation deferred.
"""

from __future__ import annotations

from typing import Any


class _RateLimiter:
    """STUB: PNCP rate limiter.

    Full implementation in scripts/crawl/rate_limiter.py (future).
    """

    async def acquire(self, timeout: float = 5.0) -> None:
        """Acquire a rate limit slot."""
        pass

    async def __aenter__(self) -> _RateLimiter:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


pncp_rate_limiter = _RateLimiter()


__all__ = [
    "pncp_rate_limiter",
]
