"""STUB: Ingestion checkpoint helpers.

Minimal definitions to enable imports from ingestion.checkpoint.
Full implementation deferred.
"""

from __future__ import annotations

from typing import Any


async def get_last_checkpoint(source: str, scope_key: str = "default") -> dict[str, Any] | None:
    """STUB: Get last checkpoint for a source."""
    return None


async def save_checkpoint(source: str, scope_key: str = "default", data: dict[str, Any] | None = None) -> None:
    """STUB: Save checkpoint for a source."""
    pass


async def create_ingestion_run(source: str, uf: str, modalidade_id: int) -> int:
    """STUB: Create a new ingestion run record."""
    return 0


async def complete_ingestion_run(run_id: int, stats: dict[str, Any] | None = None) -> None:
    """STUB: Mark ingestion run as completed."""
    pass


async def mark_checkpoint_failed(source: str, scope_key: str = "default") -> None:
    """STUB: Mark checkpoint as failed."""
    pass


__all__ = [
    "complete_ingestion_run",
    "create_ingestion_run",
    "get_last_checkpoint",
    "mark_checkpoint_failed",
    "save_checkpoint",
]
