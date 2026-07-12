"""STUB: Ingestion transformer.

Minimal definitions to enable imports from ingestion.transformer.
Full implementation deferred.
"""

from __future__ import annotations

from typing import Any


async def transform_batch(records: list[dict[str, Any]], source: str = "pncp") -> list[dict[str, Any]]:
    """STUB: Transform raw API records into database format."""
    return records


__all__ = [
    "transform_batch",
]
