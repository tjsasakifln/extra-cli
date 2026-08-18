"""Temporal freshness and 1.0→1.1 contract tests. Drive shipped functions."""

from __future__ import annotations

import pytest

from scripts.official_contract_semantics.constants import ACCEPTED_SCHEMA_VERSIONS, SCHEMA_VERSION, SCHEMA_VERSION_V10
from scripts.official_contract_semantics.freshness import (
    STALE_REASON_NO_BYTES,
    event_is_recent,
    is_stale_evidence,
    resolve_temporal_fields,
    strip_temporal_for_hash,
)
from scripts.official_contract_semantics.live import default_live_window
from scripts.official_contract_semantics.models import observation_from_mapping
from scripts.official_contract_semantics.serialize import content_hash
from scripts.official_contract_semantics.validate import ObservationValidationError, validate_mapping
from tests.official_contract_semantics.conftest import FIXTURE_DIR
from tests.official_contract_semantics.test_schema_and_validate import _valid_base


def test_old_event_with_current_verification_is_not_stale() -> None:
    stale, reason = is_stale_evidence(
        event_effective_at="2022-03-01T00:00:00Z",
        source_published_at="2022-03-02T00:00:00Z",
        retrieved_at="2026-08-17T12:00:00Z",
        verified_at="2026-08-17T12:00:00Z",
        as_of="2026-08-17T12:00:00Z",
        bytes_obtained=True,
    )
    assert stale is False
    assert reason == "not_stale"
    assert event_is_recent(event_effective_at="2022-03-01T00:00:00Z", now="2026-08-17T12:00:00Z") is False


def test_old_event_is_not_treated_as_recent() -> None:
    temporal = resolve_temporal_fields(
        event_effective_at="2020-01-15T00:00:00Z",
        retrieved_at="2026-08-17T12:00:00Z",
        verified_at="2026-08-17T12:00:00Z",
        bytes_obtained=True,
    )
    assert temporal.event_effective_at == "2020-01-15T00:00:00Z"
    assert temporal.retrieved_at == "2026-08-17T12:00:00Z"
    assert event_is_recent(event_effective_at=temporal.event_effective_at, now="2026-08-17T12:00:00Z") is False


def test_url_without_bytes_does_not_receive_freshness() -> None:
    temporal = resolve_temporal_fields(
        event_effective_at="2022-03-01T00:00:00Z",
        retrieved_at="2026-08-17T12:00:00Z",
        verified_at="2026-08-17T12:00:00Z",
        bytes_obtained=False,
    )
    assert temporal.retrieved_at is None
    assert temporal.verified_at is None
    stale, reason = is_stale_evidence(
        event_effective_at="2022-03-01T00:00:00Z",
        source_published_at="2022-03-01T00:00:00Z",
        retrieved_at="2026-08-17T12:00:00Z",
        verified_at="2026-08-17T12:00:00Z",
        as_of="2026-08-17T12:00:00Z",
        bytes_obtained=False,
    )
    assert stale is True
    assert reason == STALE_REASON_NO_BYTES


def test_schema_1_0_payload_still_loads() -> None:
    raw = _valid_base()
    raw["schema_version"] = SCHEMA_VERSION_V10
    raw.pop("event_effective_at", None)
    raw.pop("retrieved_at", None)
    raw.pop("verified_at", None)
    raw.pop("source_published_at", None)
    raw.pop("source_as_of", None)
    observation = validate_mapping(raw)
    assert observation.schema_version == SCHEMA_VERSION_V10
    assert SCHEMA_VERSION_V10 in ACCEPTED_SCHEMA_VERSIONS
    assert SCHEMA_VERSION in ACCEPTED_SCHEMA_VERSIONS


def test_incomplete_schema_fails_closed() -> None:
    raw = _valid_base()
    raw["schema_version"] = "official-contract-observation/0.9"
    with pytest.raises(ObservationValidationError) as exc:
        validate_mapping(raw)
    assert exc.value.code == "invalid_schema_version"


def test_1_1_fields_are_optional_and_hash_excludes_clocks() -> None:
    left = {
        "object": "contrato",
        "retrieved_at": "2026-08-17T12:00:00Z",
        "verified_at": "2026-08-17T12:00:00Z",
        "event_effective_at": "2022-01-01",
    }
    right = {
        "object": "contrato",
        "retrieved_at": "2026-08-17T18:00:00Z",
        "verified_at": "2026-08-17T18:00:00Z",
        "event_effective_at": "2022-01-01",
    }
    assert content_hash(strip_temporal_for_hash(left)) == content_hash(strip_temporal_for_hash(right))
    mapped = observation_from_mapping(_valid_base())
    assert mapped.event_effective_at or mapped.effective_at


def test_live_window_is_current_not_hardcoded_july() -> None:
    start, end = default_live_window(as_of="2026-08-17T12:00:00Z")
    assert start == "2026-07-18"
    assert end == "2026-08-17"
    custom_start, custom_end = default_live_window(start="2026-08-01", end="2026-08-10")
    assert (custom_start, custom_end) == ("2026-08-01", "2026-08-10")
    fixture = FIXTURE_DIR / "01_global_unknown_unit.json"
    assert fixture.is_file()
