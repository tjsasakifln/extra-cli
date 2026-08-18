"""Authority freshness: re-verified history is not stale_evidence."""

from __future__ import annotations

from typing import Any

from scripts.official_contract_semantics.freshness import (
    FRESHNESS_POLICY,
    TEMPORAL_HASH_EXCLUSIONS,
    TemporalFields,
    event_is_recent,
    freshness_block,
    is_stale_evidence,
    operational_clock,
    resolve_temporal_fields,
    strip_temporal_for_hash,
)

AUTHORITY_FRESHNESS_POLICY = FRESHNESS_POLICY


def dossier_freshness(
    *,
    as_of: str,
    event_effective_at: str | None,
    source_published_at: str | None,
    retrieved_at: str | None,
    verified_at: str | None,
    source_as_of: str | None,
    bytes_obtained: bool,
    max_age_hours: int = 48,
) -> dict[str, Any]:
    temporal = resolve_temporal_fields(
        event_effective_at=event_effective_at,
        source_published_at=source_published_at,
        retrieved_at=retrieved_at,
        verified_at=verified_at,
        source_as_of=source_as_of,
        bytes_obtained=bytes_obtained,
    )
    return freshness_block(temporal, as_of=as_of, bytes_obtained=bytes_obtained, max_age_hours=max_age_hours)


__all__ = [
    "AUTHORITY_FRESHNESS_POLICY",
    "TEMPORAL_HASH_EXCLUSIONS",
    "TemporalFields",
    "dossier_freshness",
    "event_is_recent",
    "is_stale_evidence",
    "operational_clock",
    "resolve_temporal_fields",
    "strip_temporal_for_hash",
]
