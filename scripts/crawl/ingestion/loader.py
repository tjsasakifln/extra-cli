"""STUB: Ingestion loader — bulk upsert and purge.

Minimal definitions to enable imports from ingestion.loader.
Full implementation deferred.
"""

from __future__ import annotations


async def bulk_upsert(
    records: list[dict],
    *,
    batch_size: int = 500,
) -> dict[str, int]:
    """STUB: Bulk upsert records into the database."""
    return {"inserted": 0, "updated": 0, "errors": 0}


async def purge_old_bids(retention_days: int = 30) -> int:
    """STUB: Purge old bid records."""
    return 0


__all__ = [
    "bulk_upsert",
    "purge_old_bids",
]
