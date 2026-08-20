"""Deterministic JSON digest for the national-coverage denominator.

Reuses the #302 canonical payload hash so catalog replay stays aligned.
Content hashes exclude wall-clock and producer envelope fields.
"""

from __future__ import annotations

from typing import Any

from scripts.national_contract_truth.national_universe import sha256_payload

CONTENT_HASH_EXCLUDED = frozenset(
    {
        "producer_sha",
        "created_at",
        "retrieved_at",
        "produced_at",
        "cost_ms",
        "latency_ms",
        "content_hash",
        "report",
    }
)


def digest(obj: Any) -> str:
    return sha256_payload(obj)


def content_hash(payload: dict[str, Any]) -> str:
    filtered = {key: value for key, value in payload.items() if key not in CONTENT_HASH_EXCLUDED}
    return digest(filtered)
