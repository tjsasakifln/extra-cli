"""STUB: pncp_client module (DEPRECATED).

DEPRECATED since 2026-07-11 (TD-3.2). Use scripts/crawl/pncp_crawler.py instead.

This stub exists only to allow imports from deprecated modules (e.g.,
scripts/crawl/bids_crawler.py) to resolve without ImportError.

Full implementation removed in favor of scripts/crawl/ architecture.
"""

from __future__ import annotations

from typing import Any


class AsyncPNCPClient:
    """STUB: Deprecated — use scripts/crawl/pncp_crawler.py instead."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError(
            "pncp_client.AsyncPNCPClient is DEPRECATED (TD-3.2). Use scripts/crawl/pncp_crawler.py instead."
        )


# PNCP timing constants (used by _parallel_mixin.py fallbacks)
PNCP_TIMEOUT_PER_MODALITY: float = 120.0
PNCP_MODALITY_RETRY_BACKOFF: float = 5.0
PNCP_TIMEOUT_PER_UF: float = 300.0
PNCP_TIMEOUT_PER_UF_DEGRADED: float = 180.0

__all__ = [
    "AsyncPNCPClient",
    "PNCP_TIMEOUT_PER_MODALITY",
    "PNCP_MODALITY_RETRY_BACKOFF",
    "PNCP_TIMEOUT_PER_UF",
    "PNCP_TIMEOUT_PER_UF_DEGRADED",
]
