"""BOFU inputs consume versioned #435/#437 contracts; fixtures are not live authority."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bofu_evidence.inputs import validate_comparable_input, validate_national_input
from scripts.bofu_evidence.models import SCHEMA, BofuInputError
from scripts.bofu_evidence.producer import build_packs
from scripts.national_coverage.evaluate import evaluate_from_dict

HANDOFF = Path(
    "exports/authority-handoff/contract-comparables/1.0/paving-nominal-14862788000150-2-000069-2026/payload.json"
)
SNAPSHOT = Path("scripts/bofu_evidence/fixtures/snapshot.json")
SLIM_NATIONAL = Path("scripts/bofu_evidence/fixtures/pr437_national.json")
SLIM_COMPARABLE = Path("scripts/bofu_evidence/fixtures/pr435_comparable.json")


def test_missing_input_is_refused() -> None:
    with pytest.raises(BofuInputError, match="missing_input"):
        build_packs()


def test_slim_fixture_is_refused_as_live_authority() -> None:
    slim = json.loads(SLIM_NATIONAL.read_text(encoding="utf-8"))
    with pytest.raises(BofuInputError, match="schema_version_mismatch"):
        validate_national_input(slim, synthetic=False)


def test_evaluate_payload_is_accepted_as_live_national_input() -> None:
    coverage = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    validated = validate_national_input(coverage, synthetic=False)
    assert validated["verdict"] == "PARTIAL"
    assert validated["national_claim_authorized"] is False
    assert validated["schema_version"] == "national-coverage/1.0"
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    comparable = json.loads(HANDOFF.read_text(encoding="utf-8"))
    bundle = build_packs(
        snapshot=snapshot,
        national_coverage=coverage,
        comparable=comparable,
        as_of="2026-08-19T00:00:00Z",
        synthetic=False,
    )
    assert bundle["schema"] == SCHEMA
    assert len(bundle["packs"]) == 8
    budget = next(item for item in bundle["packs"] if item["family"] == "orcamento_bdi")
    assert budget["comparable_attached"] is True
    assert budget["national"] is False
    assert budget["publication"] is False
    assert budget["index"] is False
    assert budget["expires_at"] == budget["expires"]
    replay = build_packs(
        snapshot=snapshot,
        national_coverage=coverage,
        comparable=comparable,
        as_of="2026-08-19T00:00:00Z",
        synthetic=False,
    )
    assert {item["pack_id"]: item["content_hash"] for item in bundle["packs"]} == {
        item["pack_id"]: item["content_hash"] for item in replay["packs"]
    }


def test_expired_and_forbidden_national_source_are_refused() -> None:
    coverage = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    coverage = {**coverage, "expires_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(BofuInputError, match="input_expired"):
        validate_national_input(coverage, synthetic=False, now="2026-08-19T00:00:00Z")
    poisoned = {**coverage, "universe": {**(coverage.get("universe") or {}), "official_source": "extra_1093"}}
    with pytest.raises(BofuInputError, match="forbidden_national_source"):
        validate_national_input(poisoned, synthetic=False)


def test_fixture_catalog_mode_is_not_live() -> None:
    slim = json.loads(SLIM_COMPARABLE.read_text(encoding="utf-8"))
    slim["schema"] = "comparable-contracts/1.0"
    slim["catalog_mode"] = "fixture"
    with pytest.raises(BofuInputError, match="fixture_treated_as_live"):
        validate_comparable_input(slim, synthetic=False)


def test_blocked_national_attempt_holds_pack() -> None:
    coverage = evaluate_from_dict(
        json.loads(
            Path("docs/contracts/national-coverage/fixtures/official-blocked-observed.json").read_text(encoding="utf-8")
        )
    )
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    comparable = json.loads(HANDOFF.read_text(encoding="utf-8"))
    bundle = build_packs(
        snapshot=snapshot,
        national_coverage=coverage,
        comparable=comparable,
        as_of="2026-08-19T00:00:00Z",
        synthetic=False,
    )
    for pack in bundle["packs"]:
        assert pack["national"] is False
        assert pack["coverage"]["national_verdict"] == "BLOCKED"
