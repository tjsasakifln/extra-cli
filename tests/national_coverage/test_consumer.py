"""Consumer contract shape from the shipped projection."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.national_coverage.adapters import public_read_claim_facts
from scripts.national_coverage.evaluate import evaluate_from_dict

REQUIRED_CONSUMER = (
    "requested_geography",
    "requested_period",
    "requested_source",
    "requested_grain",
    "universe_id",
    "expected_partitions",
    "closed_partitions",
    "data_freshness",
    "missingness",
    "national_claim_authorized",
    "verdict",
    "reason_codes",
    "limitations",
    "provenance",
    "content_hash",
)


def test_consumer_fields_and_omitted_coverage_pct_when_official_blocked() -> None:
    blocked = evaluate_from_dict(
        json.loads(
            Path("docs/contracts/national-coverage/fixtures/official-blocked-observed.json").read_text(encoding="utf-8")
        )
    )
    consumer = blocked["consumer"]
    for field in REQUIRED_CONSUMER:
        assert field in consumer
    assert consumer["coverage_pct"] is None
    assert consumer["provenance"]["indexation_authorized"] is False
    assert consumer["provenance"]["internal_tables_exposed"] is False
    assert "indexation_not_authorized" in consumer["limitations"]
    facts = public_read_claim_facts(consumer)
    assert facts["indexation_authorized"] is False
    assert facts["national_claim_authorized"] is False
    assert facts["national_claim_allowed"] is False
    assert facts["nacional_completo"] is False


def test_consumer_coverage_pct_only_with_valid_official_denominator() -> None:
    partial = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    consumer = partial["consumer"]
    assert consumer["coverage_pct"] is not None
    assert consumer["national_claim_authorized"] is False
    assert consumer["universe_id"] == partial["national_universe_id"]
    replay = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    assert replay["consumer"]["content_hash"] == consumer["content_hash"]
