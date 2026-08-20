"""SELECT-only consumer contract for the editorial gate.

The consumer receives facts, never internal tables and never indexation
authorization. ``coverage_pct`` is omitted unless the official denominator
is valid.
"""

from __future__ import annotations

from typing import Any

from scripts.national_coverage.hashing import content_hash
from scripts.national_coverage.models import SCHEMA_VERSION, CoverageRecord
from scripts.national_coverage.policy import official_denominator_is_valid
from scripts.national_coverage.universe import universe_to_dict


def _missingness(record: CoverageRecord) -> dict[str, Any]:
    expected = record.expected_count
    closed = record.closed_count
    unconsulted = sum(1 for part in record.partitions if part.expected and not part.queried)
    return {
        "unclosed_partitions": max(expected - closed, 0),
        "unconsulted_partitions": unconsulted,
        "unmapped_publishers": record.mapping.unmapped,
        "duplicate_publishers": record.mapping.duplicate,
        "conflict_publishers": record.mapping.conflict,
        "unresolved_identities": record.mapping.unresolved_identities,
        "unknown_gaps": tuple(
            part.partition_id
            for part in record.partitions
            if part.expected and part.status == "BLOCKED" and not part.queried
        ),
    }


def _limitations(record: CoverageRecord) -> tuple[str, ...]:
    items: list[str] = [
        "indexation_not_authorized",
        "editorial_gate_facts_only",
        "six_state_national_claims_gate_unchanged",
    ]
    if record.universe.labeled_observed_corpus:
        items.append("observed_corpus_is_not_official_national")
    if record.universe.official_status == "BLOCKED":
        items.append("official_enumerator_blocked")
    if not record.national_claim_authorized:
        items.append("national_claim_not_authorized")
    if record.verdict == "PARTIAL":
        items.append("partial_coverage_is_not_national")
    return tuple(items)


def consumer_answer(record: CoverageRecord) -> dict[str, Any]:
    extra_1093 = "extra_1093_refused_as_national_denominator" in record.reason_codes
    valid = official_denominator_is_valid(
        universe_kind=record.universe.universe_kind,
        official_status=record.universe.official_status,
        expected_partitions=record.expected_count,
        extra_1093=extra_1093,
    )
    coverage_pct: float | None = None
    if valid and record.expected_count > 0:
        coverage_pct = round(100.0 * record.closed_count / record.expected_count, 4)
    payload: dict[str, Any] = {
        "contract_version": SCHEMA_VERSION,
        "requested_geography": record.request.geography,
        "requested_period": record.request.period,
        "requested_source": record.request.source,
        "requested_grain": record.request.grain,
        "universe_id": record.universe.national_universe_id,
        "expected_partitions": record.expected_count,
        "closed_partitions": record.closed_count,
        "queried_partitions": record.queried_count,
        "data_freshness": {
            "as_of": record.freshness.as_of,
            "window_hours": record.freshness.window_hours,
            "fresh_found": record.freshness.fresh_found,
            "stale_found": record.freshness.stale_found,
            "unknown_freshness": record.freshness.unknown_freshness,
            "stock_observed_found": record.stock.observed_found,
            "stock_unobserved": record.stock.unobserved,
        },
        "missingness": _missingness(record),
        "national_claim_authorized": record.national_claim_authorized,
        "verdict": record.verdict,
        "reason_codes": list(record.reason_codes),
        "limitations": list(_limitations(record)),
        "provenance": {
            "schema_version": SCHEMA_VERSION,
            "method_version": record.universe.method_version,
            "core_method_version": record.universe.core_method_version,
            "official_source": record.universe.official_source,
            "official_source_url": record.universe.official_source_url,
            "cutoff": record.universe.cutoff,
            "retrieved_at": record.universe.retrieved_at,
            "as_of": record.universe.as_of,
            "raw_hash": record.universe.raw_hash,
            "catalog_hash": record.universe.catalog_hash,
            "core_universe_id": record.universe.core_universe_id,
            "universe_kind": record.universe.universe_kind,
            "official_status": record.universe.official_status,
            "official_block_cause": record.universe.official_block_cause,
            "grain": record.universe.grain,
            "owner": record.universe.owner,
            "next_refresh": record.universe.next_refresh,
            "indexation_authorized": False,
            "internal_tables_exposed": False,
        },
    }
    if coverage_pct is not None:
        payload["coverage_pct"] = coverage_pct
    else:
        payload["coverage_pct"] = None
    payload["content_hash"] = content_hash(payload)
    return payload


def coverage_payload(record: CoverageRecord, consumer: dict[str, Any]) -> dict[str, Any]:
    corpus = record.corpus
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "national_universe_id": record.universe.national_universe_id,
        "catalog_hash": record.universe.catalog_hash,
        "raw_hash": record.universe.raw_hash,
        "verdict": record.verdict,
        "national_claim_authorized": record.national_claim_authorized,
        "reason_codes": list(record.reason_codes),
        "universe": universe_to_dict(record.universe),
        "partitions": {
            "expected": record.expected_count,
            "queried": record.queried_count,
            "closed": record.closed_count,
            "by_status": record.by_status,
        },
        "mapping": {
            "mapped": record.mapping.mapped,
            "unmapped": record.mapping.unmapped,
            "duplicate": record.mapping.duplicate,
            "conflict": record.mapping.conflict,
            "alias": record.mapping.alias,
            "unresolved_identities": record.mapping.unresolved_identities,
        },
        "stock": {
            "expected": record.stock.expected,
            "observed_found": record.stock.observed_found,
            "unobserved": record.stock.unobserved,
        },
        "freshness": {
            "window_hours": record.freshness.window_hours,
            "as_of": record.freshness.as_of,
            "fresh_found": record.freshness.fresh_found,
            "stale_found": record.freshness.stale_found,
            "unknown_freshness": record.freshness.unknown_freshness,
        },
        "corpus": None
        if corpus is None
        else {
            "snapshot_id": corpus.snapshot_id,
            "snapshot_hash": corpus.snapshot_hash,
            "as_of": corpus.as_of,
            "source": corpus.source,
            "publisher_count": corpus.publisher_count,
            "contract_count": corpus.contract_count,
            "relation": corpus.relation,
        },
        "consumer": consumer,
        "content_hash": record.content_hash,
    }
    return payload
