"""Deterministic hashing for national-claims payloads.

Reuses the #302 canonical JSON digest so universe id/hash replay the same
raws. Content hashes exclude wall-clock, producer SHA and report cost.
"""

from __future__ import annotations

from typing import Any

from scripts.national_contract_truth.national_universe import sha256_payload

CONTENT_HASH_EXCLUDED = frozenset(
    {
        "producer_sha",
        "created_at",
        "checked_at",
        "cost_ms",
        "latency_ms",
        "report",
        "content_hash",
    }
)


def digest(obj: Any) -> str:
    return sha256_payload(obj)


def content_hash(payload: dict[str, Any]) -> str:
    """Stable digest of the authorization contract, not of the report envelope."""
    filtered = {key: value for key, value in payload.items() if key not in CONTENT_HASH_EXCLUDED}
    return digest(filtered)
