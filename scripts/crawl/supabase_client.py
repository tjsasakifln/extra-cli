"""STUB: Supabase client helpers for crawl modules.

Minimal definitions to enable imports from supabase_client.
Full implementation deferred (likely in scripts/supabase_client.py).
"""

from __future__ import annotations

from typing import Any

_sb_client: Any = None


def get_supabase() -> Any:
    """STUB: Get the Supabase client instance.

    Returns:
        A Supabase client instance, or None if not configured.
    """
    global _sb_client
    if _sb_client is None:
        raise NotImplementedError(
            "supabase_client not configured. Initialize via supabase_client.init() or configure in settings."
        )
    return _sb_client


async def sb_execute(query: Any) -> Any:
    """STUB: Execute a Supabase query and return the response.

    Args:
        query: A Supabase query object (e.g., from sb.table(...).select(...))

    Returns:
        Query result with .data attribute.
    """
    raise NotImplementedError("supabase_client not configured")


def init(url: str | None = None, key: str | None = None) -> None:
    """STUB: Initialize the Supabase client.

    Args:
        url: Supabase project URL.
        key: Supabase API key (service_role or anon).
    """
    global _sb_client
    try:
        from supabase import create_client

        _sb_client = create_client(url or "", key or "")
    except (ImportError, Exception):
        import logging

        logging.getLogger(__name__).warning(
            "Supabase client init failed (supabase package may not be installed)", exc_info=True
        )


__all__ = [
    "get_supabase",
    "sb_execute",
    "init",
]
