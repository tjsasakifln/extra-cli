"""Drive shipped produce() with injectable fixtures. Failures never confirm absence."""

from __future__ import annotations

import json

import pytest

from scripts.public_integrity.cli import replay_fixture
from scripts.public_integrity.models import INTEGRITY_STATES
from tests.public_integrity.helpers import FAILURE_FIXTURES, FIXTURES, INVALID_CNPJ, VALID_CNPJ


def _replay(name: str, cnpj: str = VALID_CNPJ) -> dict:
    return replay_fixture(FIXTURES / name, cnpj=cnpj)


def test_occurrence_is_matches_found_with_official_record() -> None:
    payload = _replay("matches.json")
    assert payload["aggregate_state"] == "MATCHES_FOUND"
    assert payload["aggregate_state"] in INTEGRITY_STATES
    assert payload["records"]
    record = payload["records"][0]
    assert record["official_id"]
    assert record["source_id"] in {"CEIS", "CNEP"}
    assert record["source_url"]
    assert record["original"]
    assert payload["sources"]["CEIS"]["official_url"]
    assert payload["sources"]["CEIS"]["authority"]


def test_both_sources_complete_empty_is_no_match_confirmed() -> None:
    payload = _replay("empty-complete.json")
    assert payload["aggregate_state"] == "NO_MATCH_CONFIRMED"
    assert payload["sources"]["CEIS"]["coverage_complete"] is True
    assert payload["sources"]["CNEP"]["coverage_complete"] is True
    assert payload["sources"]["CEIS"]["pages_fetched"] >= 1
    assert payload["sources"]["CNEP"]["pages_fetched"] >= 1
    assert payload["records"] == []


def test_multi_page_ceis_keeps_every_page_after_dedupe() -> None:
    fixture = json.loads((FIXTURES / "multi-page-ceis.json").read_text(encoding="utf-8"))
    expected_pages = len(fixture["sources"]["CEIS"]["pages"])
    payload = _replay("multi-page-ceis.json")
    assert payload["sources"]["CEIS"]["pages_fetched"] == expected_pages
    assert payload["sources"]["CEIS"]["coverage_complete"] is True
    ids = {record["official_id"] for record in payload["records"] if record["source_id"] == "CEIS"}
    assert ids == {"9001", "9002"}
    assert payload["aggregate_state"] == "MATCHES_FOUND"


@pytest.mark.parametrize("name", FAILURE_FIXTURES)
def test_failure_fixture_never_no_match_confirmed(name: str) -> None:
    payload = _replay(name)
    assert payload["aggregate_state"] in INTEGRITY_STATES
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert payload["aggregate_state"] in {"PARTIAL", "UNKNOWN"}


def test_timeout_is_partial_or_unknown() -> None:
    payload = _replay("timeout.json")
    assert payload["aggregate_state"] in {"PARTIAL", "UNKNOWN"}
    assert "timeout" in payload["sources"]["CEIS"]["reason_codes"]
    assert payload["sources"]["CNEP"]["coverage_complete"] is True


def test_429_exhausted_is_not_no_match() -> None:
    payload = _replay("rate-limit-429.json")
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert "rate_limit_exhausted" in payload["sources"]["CEIS"]["reason_codes"]
    assert payload["sources"]["CEIS"]["attempts"] >= 2


def test_5xx_is_not_no_match() -> None:
    payload = _replay("http-5xx.json")
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert "http_5xx" in payload["sources"]["CEIS"]["reason_codes"]


def test_schema_drift_is_not_no_match() -> None:
    payload = _replay("schema-drift.json")
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert "schema_drift" in payload["sources"]["CEIS"]["reason_codes"]


def test_parse_incomplete_keeps_good_record_and_is_partial() -> None:
    payload = _replay("parse-incomplete.json")
    assert payload["aggregate_state"] == "PARTIAL"
    assert payload["records"]
    assert payload["records"][0]["official_id"] == "9001"
    assert "parse_incomplete" in payload["sources"]["CEIS"]["reason_codes"]


def test_incomplete_pagination_is_partial_with_matches() -> None:
    payload = _replay("incomplete-pagination.json")
    assert payload["aggregate_state"] == "PARTIAL"
    assert payload["records"]
    assert payload["sources"]["CEIS"]["coverage_complete"] is False


def test_one_source_down_keeps_positive_matches() -> None:
    payload = _replay("source-degraded.json")
    assert payload["aggregate_state"] in {"PARTIAL", "UNKNOWN"}
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert payload["records"]
    assert payload["sources"]["CEIS"]["coverage_complete"] is True
    assert payload["sources"]["CEIS"]["status"] == "MATCHES_FOUND"
    assert payload["sources"]["CNEP"]["coverage_complete"] is False


def test_stale_cache_is_not_current() -> None:
    payload = _replay("stale-cache.json")
    assert payload["freshness"]["is_current"] is False
    assert payload["freshness"]["status"] in {"stale", "expired"}
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert "cache_expired" in payload["reason_codes"] or "stale_cache" in payload["reason_codes"]
    assert "not_current" in payload["reason_codes"]


def test_invalid_cnpj_is_not_no_match() -> None:
    payload = _replay("empty-complete.json", cnpj=INVALID_CNPJ)
    assert payload["aggregate_state"] == "UNKNOWN"
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert "invalid_cnpj" in payload["reason_codes"]
    assert payload["sources"]["CEIS"]["coverage_complete"] is False
    assert payload["sources"]["CNEP"]["coverage_complete"] is False
