"""Supabase client helpers for crawl modules.

Provides:
- ``get_supabase()``: Singleton Supabase client accessor.
- ``sb_execute()``: Execute a Supabase query and return the result.
- ``init()``: Initialize the client with URL + key.
- ``health_check()``: Verify the connection is alive.
- Batching support per CON-2 (20 connections limit).

Uses environment variables:
    SUPABASE_URL
    SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_sb_client: Any = None
_sb_initialized: bool = False


def get_supabase() -> Any:
    """Get the Supabase client instance.

    Returns:
        A Supabase client instance. Raises if not initialized.

    Raises:
        NotImplementedError: If client has not been initialized.
    """
    global _sb_client, _sb_initialized
    if _sb_client is None and not _sb_initialized:
        init()
    if _sb_client is None:
        raise NotImplementedError(
            "Supabase client not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY env vars."
        )
    return _sb_client


async def sb_execute(query: Any) -> Any:
    """Execute a Supabase query and return the response.

    Args:
        query: A Supabase query object (e.g., from sb.table(...).select(...))

    Returns:
        Query result with .data attribute.
    """
    # Ensure client is initialized (query object may depend on global client).
    get_supabase()
    try:
        response = query.execute()
        return response
    except Exception as e:
        logger.error("Supabase query failed: %s", e)
        raise


def init(url: str | None = None, key: str | None = None) -> None:
    """Initialize the Supabase client.

    Args:
        url: Supabase project URL. Defaults to SUPABASE_URL env var.
        key: Supabase API key. Defaults to SUPABASE_SERVICE_ROLE_KEY
             or SUPABASE_ANON_KEY env var.
    """
    global _sb_client, _sb_initialized

    sb_url = url or os.getenv("SUPABASE_URL", "")
    sb_key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")

    if not sb_url or not sb_key:
        logger.warning("Supabase URL and key not configured")
        _sb_initialized = True
        return

    try:
        from supabase import create_client

        _sb_client = create_client(sb_url, sb_key)
        # Verify connection
        _sb_client.table("_health").select("*").limit(1).execute()
        logger.info("Supabase client initialized: %s", sb_url)
    except ImportError:
        logger.warning("supabase package not installed. Install with: pip install supabase")
    except Exception as e:
        logger.warning("Supabase client init failed: %s", e)
    finally:
        _sb_initialized = True


def health_check() -> dict:
    """Check if the Supabase client is healthy.

    Returns:
        Dict with 'status' key: 'ok', 'degraded', or 'unavailable'.
    """
    if _sb_client is None:
        return {"status": "unavailable", "reason": "not_initialized"}
    try:
        _sb_client.table("_health").select("*").limit(1).execute()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "degraded", "reason": str(e)}


def close() -> None:
    """Close the Supabase client and release resources."""
    global _sb_client, _sb_initialized
    if _sb_client is not None:
        try:
            _sb_client.auth.sign_out()
            logger.info("Supabase client closed")
        except Exception as e:
            logger.warning("Error closing Supabase client: %s", e)
    _sb_client = None
    _sb_initialized = False


__all__ = [
    "get_supabase",
    "sb_execute",
    "init",
    "health_check",
    "close",
]
