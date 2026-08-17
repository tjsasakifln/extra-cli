"""Fail-closed validation of the versioned observation schema."""

from __future__ import annotations

import pytest

from scripts.official_contract_semantics.constants import SCHEMA_VERSION, VALUE_SEMANTICS
from scripts.official_contract_semantics.extract import extract_path
from scripts.official_contract_semantics.validate import ObservationValidationError, validate_mapping
from tests.official_contract_semantics.conftest import FIXTURE_DIR


def _valid_base() -> dict[str, object]:
    return extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0].as_dict()


def test_schema_version_and_required_fields_exist() -> None:
    observation = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0]
    payload = observation.as_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    for key in (
        "observation_id",
        "source_system",
        "source_kind",
        "official_url",
        "source_document_id",
        "source_document_sha256",
        "process_identifier",
        "contracting_entity_identifier",
        "supplier_identifier",
        "contract_identifier",
        "observed_at",
        "effective_at",
        "extractor_version",
        "locator",
        "evidence_excerpt",
        "raw_record_hash",
        "object_text",
        "lot_identifier",
        "item_identifier",
        "unit",
        "quantity",
        "execution_regime",
        "procurement_modality",
        "currency",
        "value_amount",
        "value_semantic",
        "period_start",
        "period_end",
        "amendment_type",
        "amendment_value_delta",
        "amendment_term_delta",
        "confidence_class",
        "conflict_group_id",
        "status",
    ):
        assert key in payload
    assert payload["unit"] is None
    assert payload["quantity"] is None
    assert payload["value_semantic"] == "valor_global"
    assert payload["value_semantic"] in VALUE_SEMANTICS


def test_rejects_missing_official_identity() -> None:
    raw = _valid_base()
    raw["official_url"] = None
    raw["source_document_id"] = None
    raw["source_document_sha256"] = None
    raw["contract_identifier"] = None
    with pytest.raises(ObservationValidationError) as exc:
        validate_mapping(raw)
    assert exc.value.code == "missing_official_identity"


def test_rejects_value_without_semantic() -> None:
    result = extract_path(FIXTURE_DIR / "12_value_without_semantic.json")
    assert result.observations == ()
    assert any(item.code == "value_without_semantic" for item in result.rejections)


def test_rejects_absence_inference() -> None:
    result = extract_path(FIXTURE_DIR / "13_absence_inference.json")
    assert result.observations == ()
    assert any(item.code == "inferred_from_absence" for item in result.rejections)


def test_rejects_inferred_unit() -> None:
    raw = _valid_base()
    raw["unit_inferred"] = True
    raw["unit"] = "BRL_TOTAL"
    with pytest.raises(ObservationValidationError) as exc:
        validate_mapping(raw)
    assert exc.value.code == "inferred_unit_or_quantity"
