"""SELECT-only facts for extra-cli#400 public-read consumers.

Does not import comparables engines and does not authorize indexation.
"""

from __future__ import annotations

from typing import Any


def public_read_claim_facts(consumer: dict[str, Any]) -> dict[str, Any]:
    authorized = bool(consumer.get("national_claim_authorized"))
    return {
        "schema": "national-coverage/1.0",
        "national_universe_id": consumer.get("universe_id"),
        "catalog_hash": (consumer.get("provenance") or {}).get("catalog_hash"),
        "reconciliation_hash": (consumer.get("provenance") or {}).get("reconciliation_hash"),
        "source": (consumer.get("provenance") or {}).get("official_source"),
        "cutoff": (consumer.get("provenance") or {}).get("cutoff"),
        "as_of": (consumer.get("provenance") or {}).get("as_of"),
        "method_version": (consumer.get("provenance") or {}).get("method_version"),
        "nacional_completo": authorized,
        "national_claim_allowed": authorized,
        "national_claim_authorized": authorized,
        "verdict": consumer.get("verdict"),
        "reason_codes": list(consumer.get("reason_codes") or []),
        "coverage_pct": consumer.get("coverage_pct"),
        "expected_partitions": consumer.get("expected_partitions"),
        "closed_partitions": consumer.get("closed_partitions"),
        "indexation_authorized": False,
        "editorial_gate_facts_only": True,
    }


CONSUMER_SELECT_SQL = """
SELECT
    requested_geography,
    requested_period,
    requested_source,
    requested_grain,
    universe_id,
    expected_partitions,
    closed_partitions,
    coverage_pct,
    national_claim_authorized,
    verdict,
    reason_codes,
    limitations,
    provenance,
    content_hash
FROM public.national_coverage_consumer_v1
WHERE universe_id = %s
  AND requested_geography = %s
  AND requested_period = %s
  AND requested_source = %s
  AND requested_grain = %s
ORDER BY produced_at DESC
LIMIT 1
"""
