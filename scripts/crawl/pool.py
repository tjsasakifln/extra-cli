"""Connection pool manager for HTTP crawlers.

Manages a semaphore-limited pool of concurrent connections per source.
Ensures that at most ``max_size`` connections are open simultaneously,
preventing resource exhaustion and respecting API rate limits.

Integrates with ``AdaptivePacer`` from ``pacing.py`` and
``BaseHTTPClient`` from ``clients.base``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from scripts.crawl.metrics import POOL_ACTIVE_CONNECTIONS, POOL_WAITING_REQUESTS

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Manages a bounded pool of concurrent connections for a single source.

    Uses an asyncio ``Semaphore`` to enforce the maximum number of
    in-flight requests. Tracks active and waiting counts for metrics.

    Parameters
    ----------
    source_name : str
        Logical name of the source (for metrics labels).
    max_size : int
        Maximum number of concurrent connections (default 5).
    timeout : float
        Maximum seconds to wait for a connection slot (default 30.0).
        If exceeded, a ``PoolTimeoutError`` is raised.
    """

    def __init__(
        self,
        source_name: str,
        max_size: int = 5,
        timeout: float = 30.0,
    ):
        self.source_name = source_name
        self.max_size = max_size
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_size)
        self._active = 0
        self._waiting = 0
        self._lock = asyncio.Lock()
        self._created_at = time.time()

    @property
    def active(self) -> int:
        """Number of currently active connections."""
        return self._active

    @property
    def waiting(self) -> int:
        """Number of requests waiting for a slot."""
        return self._waiting

    @property
    def utilization(self) -> float:
        """Pool utilization as a fraction (0.0 to 1.0)."""
        return self._active / self.max_size if self.max_size > 0 else 0.0

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        """Acquire a connection slot. Blocks until one is available.

        Raises
        ------
        PoolTimeoutError
            If a slot cannot be acquired within ``timeout`` seconds.
        """
        async with self._lock:
            self._waiting += 1
            POOL_WAITING_REQUESTS.labels(pool_name=self.source_name).set(self._waiting)

        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.timeout,
            )
        except TimeoutError:
            async with self._lock:
                self._waiting -= 1
                POOL_WAITING_REQUESTS.labels(pool_name=self.source_name).set(self._waiting)
            raise PoolTimeoutError(
                f"Pool [{self.source_name}] timeout after {self.timeout}s "
                f"(active={self._active}, waiting={self._waiting})"
            )

        # We got the semaphore
        async with self._lock:
            self._waiting -= 1
            self._active += 1
            POOL_WAITING_REQUESTS.labels(pool_name=self.source_name).set(self._waiting)
            POOL_ACTIVE_CONNECTIONS.labels(pool_name=self.source_name).set(self._active)

        try:
            yield
        finally:
            self._semaphore.release()
            async with self._lock:
                self._active -= 1
                POOL_ACTIVE_CONNECTIONS.labels(pool_name=self.source_name).set(self._active)

    async def stats(self) -> dict:
        """Return pool stats for monitoring."""
        async with self._lock:
            return {
                "source": self.source_name,
                "max_size": self.max_size,
                "active": self._active,
                "waiting": self._waiting,
                "utilization": self.utilization,
                "uptime_seconds": time.time() - self._created_at,
            }


class PoolTimeoutError(Exception):
    """Raised when a connection slot cannot be acquired in time."""


class PoolManager:
    """Manages multiple ``ConnectionPool`` instances, one per source.

    Provides a factory method to get or create a pool for a given source.

    Usage::

        manager = PoolManager()
        async with manager.get("pncp", max_size=5).acquire():
            # make HTTP request
            ...
    """

    def __init__(self) -> None:
        self._pools: dict[str, ConnectionPool] = {}
        self._lock = asyncio.Lock()

    def get(self, source_name: str, max_size: int = 5, timeout: float = 30.0) -> ConnectionPool:
        """Get or create a pool for the given source.

        If the pool already exists, ``max_size`` and ``timeout`` are ignored
        (the existing pool's config is kept).
        """
        if source_name not in self._pools:
            self._pools[source_name] = ConnectionPool(
                source_name=source_name,
                max_size=max_size,
                timeout=timeout,
            )
        return self._pools[source_name]

    async def stats_all(self) -> dict[str, dict]:
        """Return stats for all managed pools."""
        result = {}
        for name, pool in self._pools.items():
            result[name] = await pool.stats()
        return result
