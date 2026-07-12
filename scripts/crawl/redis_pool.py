"""STUB: Redis connection pool.

Minimal definitions to enable imports from redis_pool.
Full implementation deferred.
"""

from __future__ import annotations

from typing import Any


async def get_redis_pool() -> Any:
    """STUB: Get the shared Redis connection pool.

    Returns:
        A Redis connection instance, or None if Redis is not configured.
    """
    return None


__all__ = [
    "get_redis_pool",
]
