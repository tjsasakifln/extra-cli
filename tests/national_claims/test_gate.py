"""Six-state gate on the shipped decide() path."""

from __future__ import annotations

from copy import deepcopy

from scripts.national_claims.gate import decide
from scripts.national_claims.hashing import content_hash
from scripts.national_claims.loader import request_from_dict
from scripts.national_claims.models import AUTHORIZATION_STATES
from scripts.national_claims.sample_fixtures import (
    fixture_authorized_limited,
    fixture_authorized_national,
    fixture_needs_data,
    fixture_source_wide_only,
    fixture_stale_lkg,
)


def test_national_incomplete_is_needs_data_not_authorized() -> None:
    payload = decide(request_from_dict(fixture_needs_data()))
    assert payload["authorization_state"] == "NEEDS_DATA"
    assert payload["authorization_state"] in AUTHORIZATION_STATES
    assert payload["nacional_completo"] is False
    assert payload["consumer_view"] == "blocked"
    assert "unknown_partitions" in payload["reason_codes"]
    assert "national_denominator_incomplete" in payload["reason_codes"]
    assert payload["extra_1093_used_as_denominator"] is False
    assert payload["row_count_used_as_completeness"] is False
    assert payload["denominator"] == 3
    assert payload["numerator"] < payload["denominator"]


def test_geo_limited_claim_is_allowed_without_national_label() -> None:
    payload = decide(request_from_dict(fixture_authorized_limited()))
    assert payload["authorization_state"] == "AUTHORIZED_WITH_LIMITATIONS"
    assert payload["nacional_completo"] is False
    assert payload["scope"] == "geo_limited"
    assert payload["geography"] == "SC"
    assert "not_a_national_claim" in payload["limitations"]
    assert payload["consumer_view"] == "current"


def test_row_count_completeness_is_blocked() -> None:
    document = fixture_authorized_national()
    document["claim"]["infer_completeness_from_row_count"] = True
    payload = decide(request_from_dict(document))
    assert payload["authorization_state"] == "BLOCKED"
    assert payload["nacional_completo"] is False
    assert "row_count_completeness_forbidden" in payload["reason_codes"]


def test_extra_1093_as_national_denominator_is_blocked() -> None:
    document = fixture_needs_data()
    document["claim"]["denominator_kind"] = "extra_1093_monitored"
    payload = decide(request_from_dict(document))
    assert payload["authorization_state"] == "BLOCKED"
    assert payload["nacional_completo"] is False
    assert payload["extra_1093_used_as_denominator"] is True
    assert "forbidden_national_denominator" in payload["reason_codes"]


def test_observed_corpus_is_not_national_denominator() -> None:
    document = fixture_needs_data()
    document["claim"]["denominator_kind"] = "observed_corpus"
    payload = decide(request_from_dict(document))
    assert payload["authorization_state"] == "BLOCKED"
    assert payload["observed_corpus_used_as_denominator"] is True


def test_national_scope_with_uf_geography_is_blocked() -> None:
    document = fixture_authorized_limited()
    document["claim"]["scope"] = "national"
    document["claim"]["geography"] = "SC"
    payload = decide(request_from_dict(document))
    assert payload["authorization_state"] == "BLOCKED"
    assert payload["nacional_completo"] is False
    assert "inconsistent_scope_geography" in payload["reason_codes"]


def test_fixture_closed_national_is_authorized_only_on_versioned_denominator() -> None:
    payload = decide(request_from_dict(fixture_authorized_national()))
    assert payload["authorization_state"] == "AUTHORIZED"
    assert payload["nacional_completo"] is True
    assert payload["consumer_view"] == "current"
    assert payload["partitions_closed"] == payload["partitions_expected"]
    assert payload["extra_1093_used_as_denominator"] is False


def test_source_wide_only_is_not_authorized_national() -> None:
    payload = decide(request_from_dict(fixture_source_wide_only()))
    assert payload["authorization_state"] in AUTHORIZATION_STATES
    assert payload["authorization_state"] != "AUTHORIZED"
    assert payload["nacional_completo"] is False
    assert payload["identity"]["proves_entity_coverage"] is False


def test_payload_content_hash_is_stable() -> None:
    request = request_from_dict(fixture_needs_data())
    first = decide(request)
    second = decide(request)
    assert first["authorization_state"] == second["authorization_state"]
    assert first["reason_codes"] == second["reason_codes"]
    assert first["content_hash"] == second["content_hash"]
    assert first["content_hash"] == content_hash(first)


def test_stale_with_valid_lkg_does_not_authorize_current() -> None:
    payload = decide(request_from_dict(fixture_stale_lkg()))
    assert payload["authorization_state"] == "STALE"
    assert payload["nacional_completo"] is False
    assert payload["consumer_view"] == "lkg"
    assert payload["lkg_ref"] is not None
    assert payload["lkg_status"] == "valid"
    assert "freshness_stale" in payload["reason_codes"]


def test_failed_partition_yields_failed() -> None:
    document = deepcopy(fixture_authorized_national())
    document["partitions"][0]["status"] = "FAILED"
    document["partitions"][0]["reason"] = "http_500"
    payload = decide(request_from_dict(document))
    assert payload["authorization_state"] == "FAILED"
    assert payload["nacional_completo"] is False
    assert "failed_partitions" in payload["reason_codes"]
