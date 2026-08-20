"""Contract twin and shipped constants stay aligned."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bofu_evidence.models import (
    EPISTEMIC_CLASSES,
    FAMILIES,
    PACK_STATES,
    REQUIRED_PACK_FIELDS,
    SCHEMA,
)

REPO = Path(__file__).resolve().parents[2]
CONTRACT_JSON = REPO / "docs" / "contracts" / "bofu-evidence-v1.json"
CONTRACT_MD = REPO / "docs" / "contracts" / "bofu-evidence-v1.md"


def test_contract_files_exist_and_declare_schema() -> None:
    assert CONTRACT_JSON.is_file()
    assert CONTRACT_MD.is_file()
    contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
    assert contract["schema"] == SCHEMA
    assert contract["schema"] == "public-read-bofu-evidence/1.0"
    markdown = CONTRACT_MD.read_text(encoding="utf-8")
    assert SCHEMA in markdown
    assert "python3 -m scripts.bofu_evidence" in markdown


def test_contract_lists_eight_families_and_default_false_flags() -> None:
    contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
    assert list(contract["families"]) == list(FAMILIES)
    assert len(contract["families"]) == 8
    assert set(contract["epistemic_classes"]) == set(EPISTEMIC_CLASSES)
    assert set(contract["states"]) == set(PACK_STATES)
    assert contract["authorization"]["publication"] is False
    assert contract["authorization"]["index"] is False
    assert contract["authorization"]["national"] is False
    assert contract["national_coverage"]["verdict"] == "PARTIAL"
    assert contract["national_coverage"]["national_claim_authorized"] is False
    assert list(contract["required_pack_fields"]) == list(REQUIRED_PACK_FIELDS)
    assert "expires_at" in contract["required_pack_fields"]
    assert "docs/contracts/national-coverage/national-coverage-v1.json" in contract["consumes_public_contracts"]
    assert "scripts.contract_comparables.engine" in contract["does_not_import"]
