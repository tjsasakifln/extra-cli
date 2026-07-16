"""Redis connection pool with graceful fallback.

Provides:
- ``RedisPool``: Async connection pool with lifecycle management.
- ``get_redis_pool()``: Singleton accessor.
- Graceful fallback when Redis is unavailable (CON-6).

Uses environment variables:
    REDIS_URL (default: redis://localhost:6379/0)
    REDIS_POOL_SIZE (default: 10)
    REDIS_TIMEOUT (default: 5s)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", "10"))
REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "5"))

# ---------------------------------------------------------------------------
# Pool state
# ---------------------------------------------------------------------------

_pool: Any = None
_fallback_active = False


async def get_redis_pool() -> Any:
    """Get the shared Redis connection pool.

    Returns:
        A Redis connection instance, or None if Redis is not configured
        or unavailable (graceful fallback per CON-6).
    """
    global _pool, _fallback_active

    if _pool is not None:
        return _pool

    if _fallback_active:
        return None

    try:
        import redis.asyncio as aioredis

        _pool = aioredis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=REDIS_POOL_SIZE,
            socket_connect_timeout=REDIS_TIMEOUT,
            socket_timeout=REDIS_TIMEOUT,
            retry_on_timeout=True,
        )
        # Test connectivity
        r = aioredis.Redis(connection_pool=_pool)
        await r.ping()
        await r.aclose()
        logger.info("Redis pool created: %s (max %d)", REDIS_URL, REDIS_POOL_SIZE)
        return _pool
    except Exception as e:
        logger.warning("Redis unavailable, falling back (CON-6): %s", e)
        _pool = None
        _fallback_active = True
        return None


async def close_redis_pool() -> None:
    """Close the Redis connection pool."""
    global _pool, _fallback_active
    if _pool is not None:
        try:
            await _pool.disconnect()
            logger.info("Redis pool closed")
        except Exception as e:
            logger.warning("Error closing Redis pool: %s", e)
    _pool = None
    _fallback_active = False


def is_redis_available() -> bool:
    """Check if Redis is available (not in fallback mode)."""
    global _fallback_active
    return not _fallback_active and _pool is not None


__all__ = [
    "get_redis_pool",
    "close_redis_pool",
    "is_redis_available",
]
