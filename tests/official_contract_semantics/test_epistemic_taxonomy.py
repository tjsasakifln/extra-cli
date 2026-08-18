"""Adversarial proofs of the shipped epistemic taxonomy. No parallel oracle."""

from __future__ import annotations

from decimal import Decimal

from scripts.official_contract_semantics.constants import (
    DERIVATION_COMPARABLES_CANONICAL,
    EPISTEMIC_FACT_OFFICIAL,
    EPISTEMIC_NOT_APPLICABLE,
    EPISTEMIC_NOT_FOUND,
    EPISTEMIC_OBSERVATION_DERIVED,
    EPISTEMIC_UNAVAILABLE,
    EPISTEMIC_UNKNOWN,
    SCHEMA_VERSION,
)
from scripts.official_contract_semantics.coverage import contract_hold_report, field_epistemic
from scripts.official_contract_semantics.export_comparables import export_comparables_corpus
from scripts.official_contract_semantics.export_publication import export_publication_evidence
from scripts.official_contract_semantics.extract import extract_path, extract_payload, extract_text
from scripts.official_contract_semantics.identity import normalize_cnpj
from scripts.official_contract_semantics.reconcile import reconcile
from tests.official_contract_semantics.conftest import FIXTURE_DIR

_BASE = {
    "source_system": "pncp",
    "source_kind": "contract",
    "official_url": "https://pncp.gov.br/app/contratos/83102277000152-1-000099/2025",
    "source_document_id": "doc-taxonomy",
    "contract_identifier": "83102277000152-1-000099/2025",
    "contracting_entity_identifier": "83102277000152",
    "object_text": "Contrato de prova taxonômica",
}


def test_schema_exposes_epistemic_taxonomy() -> None:
    item = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0]
    assert item.schema_version == SCHEMA_VERSION
    assert item.epistemic_class == EPISTEMIC_FACT_OFFICIAL
    assert item.field_epistemics["value_semantic"] == EPISTEMIC_FACT_OFFICIAL
    assert item.field_epistemics["unit"] == EPISTEMIC_UNKNOWN
    assert item.field_epistemics["quantity"] == EPISTEMIC_UNKNOWN
    assert item.unit is None
    assert item.quantity is None


def test_explicit_not_applicable_is_not_inferred_from_global_regime() -> None:
    global_item = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0]
    assert field_epistemic(global_item, "unit") == EPISTEMIC_UNKNOWN
    marked = extract_payload(
        {
            **_BASE,
            "valor_global": "750000.00",
            "currency": "BRL",
            "execution_regime": "empreitada_global",
            "procurement_modality": "pregao_eletronico",
            "period_start": "2025-02-01",
            "period_end": "2026-02-01",
            "not_applicable_fields": ["unit", "quantity"],
        }
    ).observations[0]
    assert marked.unit is None
    assert marked.quantity is None
    assert marked.field_epistemics["unit"] == EPISTEMIC_NOT_APPLICABLE
    assert marked.field_epistemics["quantity"] == EPISTEMIC_NOT_APPLICABLE
    report = contract_hold_report([marked])
    assert "missing_unit" not in report[0]["reason_codes"]
    assert report[0]["technically_eligible_for_engine"] is True


def test_same_record_two_value_fields_emits_both_facts() -> None:
    result = extract_payload(
        {
            **_BASE,
            "valor_global": "540000.00",
            "valor_mensal": "45000.00",
            "currency": "BRL",
        }
    )
    semantics = {item.value_semantic for item in result.observations}
    amounts = {item.value_amount for item in result.observations}
    assert semantics == {"valor_global", "valor_mensal"}
    assert amounts == {Decimal("540000.00"), Decimal("45000.00")}
    assert all(item.epistemic_class == EPISTEMIC_FACT_OFFICIAL for item in result.observations)
    reconciled = reconcile(result.observations)
    assert all(item.status == "observed" for item in reconciled)


def test_conflicting_labeled_amounts_are_rejected_not_elected() -> None:
    result = extract_text(
        "Valor global: 100000,00\nValor global: 180000,00",
        identity=_BASE,
    )
    assert result.observations == ()
    assert any(item.code == "conflicting_labeled_values" for item in result.rejections)


def test_unknown_source_kind_is_rejected_not_coerced() -> None:
    result = extract_payload({**_BASE, "source_kind": "spreadsheet_export", "valor_global": "10.00"})
    assert result.observations == ()
    assert any(item.code == "invalid_source_kind" for item in result.rejections)


def test_unknown_value_semantic_is_rejected_not_aliased() -> None:
    result = extract_payload(
        {
            **_BASE,
            "value_amount": "10.00",
            "value_semantic": "valor_reajuste",
        }
    )
    assert result.observations == ()
    assert any(item.code == "invalid_value_semantic" for item in result.rejections)


def test_masked_and_incomplete_cnpj_stay_unknown() -> None:
    result = extract_payload(
        {
            **_BASE,
            "supplier_identifier": "12.***.***/0001-**",
            "valor_global": "1000.00",
            "currency": "BRL",
        }
    )
    assert result.observations
    item = result.observations[0]
    assert item.supplier_identifier is None
    assert item.extra.get("supplier_identifier_masked") is True
    assert normalize_cnpj("12.***.***/0001-**") is None
    assert normalize_cnpj("123") is None
    assert normalize_cnpj("83102277000152") == "83102277000152"


def test_ambiguous_date_is_not_stored_as_fact() -> None:
    result = extract_payload(
        {
            **_BASE,
            "valor_global": "1000.00",
            "currency": "BRL",
            "period_start": "01/02/03",
            "period_end": "fevereiro de 2025",
            "effective_at": "2025-03-01T12:00:00-03:00",
        }
    )
    item = result.observations[0]
    assert item.period_start is None
    assert item.period_end is None
    assert item.effective_at == "2025-03-01T12:00:00-03:00"
    assert "unparsed_dates" in item.extra
    assert item.field_epistemics["period_start"] == EPISTEMIC_UNKNOWN


def test_similar_contract_numbers_do_not_collapse() -> None:
    result = extract_payload(
        [
            {
                **_BASE,
                "source_document_id": "doc-base",
                "contract_identifier": "83102277000152-1-000001/2025",
                "valor_global": "100.00",
            },
            {
                **_BASE,
                "source_document_id": "doc-aditivo",
                "source_kind": "amendment",
                "contract_identifier": "83102277000152-1-000001/2025-ADITIVO-1",
                "amendment_type": "valor",
                "amendment_value_delta": "10.00",
            },
            {
                **_BASE,
                "source_document_id": "doc-apostila",
                "contract_identifier": "83102277000152-1-000001/2025-APOSTILA",
                "valor_global": "110.00",
            },
        ]
    )
    ids = {item.contract_identifier for item in result.observations}
    assert len(ids) == 3
    reconciled = reconcile(result.observations)
    assert all(item.status == "observed" for item in reconciled)


def test_http_404_is_not_found_and_does_not_assert_world_absence() -> None:
    result = extract_path(FIXTURE_DIR / "09_unavailable_url.json")
    assert result.observations == ()
    assert result.unavailabilities
    item = result.unavailabilities[0]
    assert item.epistemic_class == EPISTEMIC_NOT_FOUND
    assert item.asserts_world_absence is False
    assert item.recorded_as == "unavailable"
    assert item.search_contract["bound"] == "single_official_url"


def test_dsn_style_unavailability_is_unavailable_not_not_found() -> None:
    from scripts.official_contract_semantics.models import SourceUnavailability

    item = SourceUnavailability(
        official_url="postgresql://local/pncp_supplier_contracts",
        error_kind="dsn_unavailable",
        message="LOCAL_DATALAKE_DSN absent",
    )
    assert item.epistemic_class == EPISTEMIC_UNAVAILABLE
    assert item.asserts_world_absence is False


def test_export_marks_canonical_projection_as_derived() -> None:
    item = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0]
    assert item.value_semantic == "valor_global"
    assert item.epistemic_class == EPISTEMIC_FACT_OFFICIAL
    corpus = export_comparables_corpus([item])
    record = corpus["cases"]["official_semantics_export"]["contracts"][0]
    assert record["valor_semantic"] == "valor_integral_nominal"
    assert record["extra_epistemic_class"] == EPISTEMIC_OBSERVATION_DERIVED
    assert record["extra_derivation_method"] == DERIVATION_COMPARABLES_CANONICAL
    assert record["extra_source_epistemic_class"] == EPISTEMIC_FACT_OFFICIAL
    blob = str(corpus).casefold()
    for forbidden in (
        "crédito tributário",
        "direito a crédito",
        "pleito",
        "reajuste devido",
        "irregularidade",
        "incapaz",
        "inadimpl",
        "melhor escolha",
        "aproveite",
    ):
        assert forbidden not in blob


def test_publication_export_never_authorizes_index() -> None:
    item = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0]
    snapshot = export_publication_evidence([item])
    assert snapshot["authorizes_publication"] is False
    assert snapshot["authorizes_indexation"] is False
    assert snapshot["records"][0]["epistemic_class"] == EPISTEMIC_FACT_OFFICIAL
    assert {"INDEX", "PUBLISHABLE_INDEX", "PUBLISHABLE_NOINDEX"}.issubset(set(snapshot["does_not_emit"]))
