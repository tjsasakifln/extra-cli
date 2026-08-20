"""Produced payload validates against the shipped contract."""

from __future__ import annotations

from pathlib import Path

from scripts.public_integrity.cli import replay_fixture
from scripts.public_integrity.models import PAYLOAD_FIELDS, SCHEMA_VERSION
from scripts.public_integrity.schema import load_contract, load_schema, validate_payload
from tests.public_integrity.helpers import FIXTURES, VALID_CNPJ


def test_contract_files_exist() -> None:
    root = Path("docs/contracts")
    assert (root / "public-read-integrity-v1.md").is_file()
    assert (root / "public-read-integrity-v1.json").is_file()
    assert (root / "public-read-integrity-v1.schema.json").is_file()
    contract = load_contract()
    assert contract["schema_version"] == SCHEMA_VERSION
    assert contract["aggregate_states"] == ["MATCHES_FOUND", "NO_MATCH_CONFIRMED", "PARTIAL", "UNKNOWN"]
    schema = load_schema()
    assert schema["properties"]["schema"]["const"] == SCHEMA_VERSION


def test_matches_and_empty_payloads_validate() -> None:
    for name in ("matches.json", "empty-complete.json"):
        payload = replay_fixture(FIXTURES / name, cnpj=VALID_CNPJ)
        errors = validate_payload(payload)
        assert errors == [], errors
        for field in PAYLOAD_FIELDS:
            assert field in payload
        assert payload["not_legal_conclusion"] is True
