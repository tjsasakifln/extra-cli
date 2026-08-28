"""Drive COMMERCIAL_AUTHORITY/1.0 on the shipped classifier. Clock is injected."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.confenge_activation.commercial_authority import (
    CONTRACT_VERSION,
    DEFAULT_POLICY,
    POLICY_VERSION,
    CommercialAuthorityBinding,
    authority_from_manifest,
    classify_commercial_authority,
    historical_source_was_proven_fresh,
    root_transport_allowed,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
BINDING = CommercialAuthorityBinding(
    basis_source_run_id="run-snapshot-a",
    basis_snapshot_hash="snapshot-a",
    basis_membership_hash="membership-a",
    basis_publication_semantic_hash="semantic-a",
    producer_identity="producer-a",
)
FIXTURE_DIR = Path("docs/contracts/confenge-commercial-authority/v1/fixtures")
SCHEMA_PATH = Path("docs/contracts/confenge-commercial-authority/v1/commercial-authority-v1.schema.json")

CLOCK_CASES = (
    (timedelta(hours=23, minutes=59), "CURRENT", True, True),
    (timedelta(hours=24), "CURRENT", True, True),
    (timedelta(hours=24, minutes=1), "DEGRADED", True, True),
    (timedelta(hours=71, minutes=59), "DEGRADED", True, True),
    (timedelta(hours=72), "DEGRADED", True, True),
    (timedelta(hours=72, minutes=1), "FROZEN_FOR_NEW_ADMISSION", False, True),
    (timedelta(days=6, hours=23, minutes=59), "FROZEN_FOR_NEW_ADMISSION", False, True),
    (timedelta(days=7), "FROZEN_FOR_NEW_ADMISSION", False, True),
    (timedelta(days=7, minutes=1), "EXPIRED", False, False),
)


def test_contract_and_policy_are_versioned() -> None:
    assert CONTRACT_VERSION == "COMMERCIAL_AUTHORITY/1.0"
    assert POLICY_VERSION == "COMMERCIAL_AUTHORITY_POLICY/1.0"
    assert DEFAULT_POLICY.current_max_hours == 24.0
    assert DEFAULT_POLICY.degraded_max_hours == 72.0
    assert DEFAULT_POLICY.frozen_max_hours == 168.0


@pytest.mark.parametrize("age, state, new_admission, bound", CLOCK_CASES)
def test_injected_clock_boundaries(age: timedelta, state: str, new_admission: bool, bound: bool) -> None:
    payload = classify_commercial_authority(
        validated_at=NOW - age,
        now=NOW,
        binding=BINDING,
    )
    assert payload["state"] == state
    assert payload["new_admission_allowed"] is new_admission
    assert payload["existing_bound_touch_transport_allowed"] is bound
    assert payload["basis_snapshot_hash"] == "snapshot-a"
    assert payload["basis_membership_hash"] == "membership-a"
    assert payload["basis_source_run_id"] == "run-snapshot-a"
    assert payload["basis_publication_semantic_hash"] == "semantic-a"
    assert payload["valid_until"]
    assert payload["age_hours"] == pytest.approx(age.total_seconds() / 3600, abs=1e-6)


def test_state_matrix_reason_codes_and_valid_until() -> None:
    current = classify_commercial_authority(validated_at=NOW, now=NOW, binding=BINDING)
    assert current["reason_codes"] == ["COMMERCIAL_AUTHORITY_CURRENT"]
    assert current["valid_until"] == "2026-01-16T12:00:00Z"

    degraded = classify_commercial_authority(
        validated_at=NOW - timedelta(hours=24, minutes=1), now=NOW, binding=BINDING
    )
    assert "NEW_ADMISSION_REQUIRES_VALID_EVIDENCE_AND_NO_DRIFT" in degraded["reason_codes"]
    assert degraded["valid_until"] == "2026-01-17T11:59:00Z"

    frozen = classify_commercial_authority(validated_at=NOW - timedelta(hours=72, minutes=1), now=NOW, binding=BINDING)
    assert "NEW_ADMISSION_FROZEN" in frozen["reason_codes"]
    assert "EXISTING_BOUND_TOUCH_MAY_CONTINUE" in frozen["reason_codes"]

    expired = classify_commercial_authority(validated_at=NOW - timedelta(days=7, minutes=1), now=NOW, binding=BINDING)
    assert "ALL_NEW_TRANSPORT_EXPIRED" in expired["reason_codes"]


def test_explicit_revocation_beats_grace() -> None:
    payload = classify_commercial_authority(
        validated_at=NOW - timedelta(hours=1),
        now=NOW,
        binding=BINDING,
        explicit_revoked=True,
    )
    assert payload["state"] == "EXPIRED"
    assert payload["new_admission_allowed"] is False
    assert payload["existing_bound_touch_transport_allowed"] is False
    assert payload["reason_codes"][0] == "EXPLICIT_REVOCATION"
    assert payload["valid_until"] == "2026-01-15T12:00:00Z"
    assert payload["valid_until"] == payload["classified_at"]


def test_deactivated_root_cannot_ride_grace() -> None:
    payload = classify_commercial_authority(validated_at=NOW, now=NOW, binding=BINDING)
    allowed, reasons = root_transport_allowed(
        payload,
        cnpj_root8="12345678",
        deactivated_roots=["12345678000195"],
        new_admission=False,
    )
    assert allowed is False
    assert "ROOT_EXPLICITLY_DEACTIVATED" in reasons
    sibling, _ = root_transport_allowed(
        payload,
        cnpj_root8="87654321",
        deactivated_roots=["12345678000195"],
        new_admission=False,
    )
    assert sibling is True


@pytest.mark.parametrize(
    "field",
    (
        "basis_source_run_id",
        "basis_snapshot_hash",
        "basis_membership_hash",
        "basis_publication_semantic_hash",
        "producer_identity",
    ),
)
def test_binding_mismatch_is_unknown_and_closed(field: str) -> None:
    expected = CommercialAuthorityBinding(**{**BINDING.as_dict(), field: "other"})
    payload = classify_commercial_authority(
        validated_at=NOW,
        now=NOW,
        binding=BINDING,
        expected_binding=expected,
    )
    assert payload["state"] == "UNKNOWN"
    assert payload["new_admission_allowed"] is False
    assert payload["existing_bound_touch_transport_allowed"] is False
    assert "BINDING_MISMATCH" in payload["reason_codes"]


def test_empty_binding_hashes_are_unknown_and_closed() -> None:
    payload = classify_commercial_authority(
        validated_at=NOW,
        now=NOW,
        binding=CommercialAuthorityBinding(
            basis_source_run_id="",
            basis_snapshot_hash="",
            basis_membership_hash="",
            basis_publication_semantic_hash="",
            producer_identity="",
        ),
    )
    assert payload["state"] == "UNKNOWN"
    assert payload["new_admission_allowed"] is False
    assert payload["existing_bound_touch_transport_allowed"] is False
    assert "BINDING_MISMATCH" in payload["reason_codes"]


def test_historical_fresh_attestation_does_not_mean_live_fresh() -> None:
    historical_source_was_proven_fresh(
        {
            "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
            "status": "FRESH",
            "expires_at": "2026-01-01T00:00:00Z",
        }
    )
    with pytest.raises(ValueError, match="never proven FRESH"):
        historical_source_was_proven_fresh({"contract_version": "PNCP_CONTRACT_FRESHNESS/1.0", "status": "STALE"})


def test_golden_fixtures_match_shipped_classifier() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = schema["required"]
    for name in ("current", "degraded", "frozen", "expired"):
        fixture = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        binding = CommercialAuthorityBinding(**fixture["binding"])
        payload = classify_commercial_authority(
            validated_at=datetime.fromisoformat(fixture["validated_at"].replace("Z", "+00:00")),
            now=datetime.fromisoformat(fixture["now"].replace("Z", "+00:00")),
            binding=binding,
        )
        expected = fixture["expected"]
        assert payload["state"] == expected["state"]
        assert payload["new_admission_allowed"] is expected["new_admission_allowed"]
        assert payload["existing_bound_touch_transport_allowed"] is expected["existing_bound_touch_transport_allowed"]
        assert payload["valid_until"] == expected["valid_until"]
        assert payload["reason_codes"] == expected["reason_codes"]
        for key in required:
            assert key in payload


def test_failed_next_run_fixture_preserves_last_good_authority() -> None:
    fixture = json.loads((FIXTURE_DIR / "failed-next-run-preserves-last-good.json").read_text(encoding="utf-8"))
    last_good = fixture["last_good"]
    payload = classify_commercial_authority(
        validated_at=datetime.fromisoformat(last_good["validated_at"].replace("Z", "+00:00")),
        now=datetime.fromisoformat(fixture["now"].replace("Z", "+00:00")),
        binding=CommercialAuthorityBinding(**last_good["binding"]),
        source_operational_health=fixture["failed_attempt"]["source_operational_health"],
    )
    expected = fixture["expected"]["commercial_authority"]
    assert fixture["expected"]["new_feed_promoted"] is False
    assert fixture["failed_attempt"]["promoted"] is False
    assert payload["state"] == expected["state"]
    assert payload["new_admission_allowed"] is expected["new_admission_allowed"]
    assert payload["basis_snapshot_hash"] == expected["basis_snapshot_hash"]
    assert fixture["failed_attempt"]["source_operational_health"]["status"] == "STALE"
    assert payload["source_operational_health_hash"]


def test_warmbly_example_keeps_pncp_field_meaning() -> None:
    example = json.loads(
        Path("docs/contracts/confenge-commercial-authority/v1/examples/warmbly-manifest-authority.json").read_text(
            encoding="utf-8"
        )
    )
    freshness = example["authoritative_source_freshness"]
    assert freshness["contract_version"] == "PNCP_CONTRACT_FRESHNESS/1.0"
    assert freshness["status"] == "FRESH"
    assert example["source_operational_health"]["status"] == "STALE"
    authority = example["commercial_authority"]
    replay = authority_from_manifest(
        example,
        now=datetime.fromisoformat(authority["classified_at"].replace("Z", "+00:00")),
        producer_identity=authority["producer_identity"],
        publication_semantic_hash=authority["basis_publication_semantic_hash"],
        source_operational_health=example["source_operational_health"],
    )
    assert replay["state"] == "CURRENT"
    assert replay["new_admission_allowed"] is True
    assert authority["producer_identity"] == "producer-a"
    assert authority["basis_publication_semantic_hash"] == "semantic-a"


def test_one_byte_producer_or_semantic_drift_fails_closed() -> None:
    payload = classify_commercial_authority(validated_at=NOW, now=NOW, binding=BINDING)
    for field in ("basis_publication_semantic_hash", "producer_identity", "basis_membership_hash"):
        drifted = CommercialAuthorityBinding(**{**BINDING.as_dict(), field: payload[field][:-1] + "b"})
        closed = classify_commercial_authority(
            validated_at=NOW,
            now=NOW,
            binding=BINDING,
            expected_binding=drifted,
        )
        assert closed["state"] == "UNKNOWN"
        assert closed["new_admission_allowed"] is False
        assert closed["existing_bound_touch_transport_allowed"] is False
        assert "BINDING_MISMATCH" in closed["reason_codes"]
