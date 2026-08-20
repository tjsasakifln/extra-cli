"""Fail-closed verdicts from the shipped evaluate path."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.national_coverage.evaluate import evaluate_from_dict

FIXTURES = Path("docs/contracts/national-coverage/fixtures")


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_partial_fixture_does_not_authorize_national() -> None:
    first = evaluate_from_dict(_load("official-partial.json"))
    second = evaluate_from_dict(_load("official-partial.json"))
    assert first["verdict"] == "PARTIAL"
    assert first["national_claim_authorized"] is False
    assert first["national_universe_id"] == second["national_universe_id"]
    assert first["catalog_hash"] == second["catalog_hash"]
    assert first["content_hash"] == second["content_hash"]
    assert first["partitions"]["expected"] == 3
    assert first["partitions"]["closed"] == 2
    assert first["partitions"]["by_status"]["FOUND"] == 1
    assert first["partitions"]["by_status"]["ZERO_CONFIRMED"] == 1
    assert first["partitions"]["by_status"]["BLOCKED"] == 1
    assert "partitions_not_closed" in first["reason_codes"]
    consumer = first["consumer"]
    assert consumer["national_claim_authorized"] is False
    assert consumer["coverage_pct"] is not None
    assert 0 < consumer["coverage_pct"] < 100


def test_closed_toy_authorizes_only_when_every_partition_closes() -> None:
    payload = evaluate_from_dict(_load("official-closed-toy.json"))
    assert payload["verdict"] == "NATIONAL_CLAIM_AUTHORIZED"
    assert payload["national_claim_authorized"] is True
    assert payload["partitions"]["expected"] == payload["partitions"]["closed"]
    assert payload["partitions"]["by_status"]["BLOCKED"] == 0
    assert payload["partitions"]["by_status"]["FAILED"] == 0


def test_national_scope_against_partial_is_not_authorized() -> None:
    payload = evaluate_from_dict(_load("official-partial.json"))
    assert payload["consumer"]["requested_geography"] == "BR"
    assert payload["verdict"] != "NATIONAL_CLAIM_AUTHORIZED"
    assert payload["national_claim_authorized"] is False


def test_sc_scope_may_be_partial_but_never_flips_national_boolean() -> None:
    payload = evaluate_from_dict(_load("sc-scope.json"))
    assert payload["consumer"]["requested_geography"] == "SC"
    assert payload["verdict"] == "PARTIAL"
    assert payload["national_claim_authorized"] is False
    assert payload["partitions"]["by_status"]["NOT_APPLICABLE"] == 2
    assert payload["partitions"]["expected"] == 1
    assert payload["partitions"]["closed"] == 1
    assert "partial_does_not_authorize_national" in payload["reason_codes"]


def test_blocked_official_national_request() -> None:
    payload = evaluate_from_dict(_load("official-blocked-observed.json"))
    assert payload["verdict"] == "BLOCKED"
    assert payload["national_claim_authorized"] is False
    assert payload["universe"]["universe_kind"] == "OBSERVED_CORPUS"
    assert payload["consumer"]["coverage_pct"] is None
    assert "official_denominator_blocked" in payload["reason_codes"]
