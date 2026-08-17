"""Extract and reconcile drive the shipped functions, not a parallel oracle."""

from __future__ import annotations

from decimal import Decimal

from scripts.official_contract_semantics.extract import extract_html, extract_path, extract_payload
from scripts.official_contract_semantics.persist import append_observations
from scripts.official_contract_semantics.reconcile import reconcile
from tests.official_contract_semantics.conftest import FIXTURE_DIR


def test_global_contract_keeps_unknown_unit_and_quantity() -> None:
    result = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json")
    assert len(result.observations) == 1
    item = result.observations[0]
    assert item.unit is None
    assert item.quantity is None
    assert item.value_semantic == "valor_global"
    assert item.value_amount == Decimal("750000.00")
    assert item.status == "observed"


def test_html_table_extracts_explicit_unit_item() -> None:
    html = (FIXTURE_DIR / "html" / "02_unit_item_explicit.html").read_text(encoding="utf-8")
    identity = extract_path(FIXTURE_DIR / "02_unit_item_identity.json").observations[0].as_dict()
    identity.pop("value_amount", None)
    identity.pop("value_semantic", None)
    result = extract_html(
        html,
        identity={
            key: identity[key]
            for key in (
                "source_system",
                "source_kind",
                "official_url",
                "source_document_id",
                "contract_identifier",
                "contracting_entity_identifier",
                "supplier_identifier",
                "object_text",
                "execution_regime",
                "procurement_modality",
                "period_start",
                "period_end",
            )
        },
    )
    assert result.document_errors == ()
    assert result.observations
    item = result.observations[0]
    assert item.unit == "m2"
    assert item.quantity == Decimal("12000")
    assert item.value_semantic == "valor_unitario"
    assert item.locator.table == "table[0]"


def test_monthly_and_global_are_two_facts_not_a_winner() -> None:
    result = extract_path(FIXTURE_DIR / "03_monthly_vs_global.json")
    reconciled = reconcile(result.observations)
    semantics = {item.value_semantic for item in reconciled}
    assert semantics == {"valor_mensal", "valor_global"}
    assert all(item.status == "observed" for item in reconciled)


def test_amendment_term_and_value() -> None:
    term = extract_path(FIXTURE_DIR / "04_amendment_term.json").observations[0]
    value = extract_path(FIXTURE_DIR / "05_amendment_value.json").observations[0]
    assert term.source_kind == "amendment"
    assert term.amendment_type == "prazo"
    assert term.amendment_term_delta == "P180D"
    assert term.value_amount is None
    assert value.amendment_type == "valor"
    assert value.amendment_value_delta == Decimal("125000.00")
    assert value.value_semantic == "valor_contratado"


def test_official_conflict_is_preserved() -> None:
    result = extract_path(FIXTURE_DIR / "06_official_conflict.json")
    reconciled = reconcile(result.observations)
    assert len(reconciled) == 2
    assert {item.status for item in reconciled} == {"conflicted"}
    groups = {item.conflict_group_id for item in reconciled}
    assert len(groups) == 1
    assert None not in groups
    amounts = {item.value_amount for item in reconciled}
    assert amounts == {Decimal("900000.00"), Decimal("980000.00")}


def test_explicit_supersession_keeps_prior_row() -> None:
    result = extract_path(FIXTURE_DIR / "07_explicit_supersession.json")
    reconciled = reconcile(result.observations)
    by_doc = {item.source_document_id: item for item in reconciled}
    assert by_doc["doc-supersede-old"].status == "superseded_by_official_evidence"
    assert by_doc["doc-supersede-new"].status == "observed"
    assert len(reconciled) == 2


def test_divergent_cnpj_conflicts() -> None:
    result = extract_path(FIXTURE_DIR / "08_divergent_cnpj.json")
    reconciled = reconcile(result.observations)
    assert {item.status for item in reconciled} == {"conflicted"}
    suppliers = {item.supplier_identifier for item in reconciled}
    assert suppliers == {"77888999000127", "88999000000118"}


def test_unavailable_url_is_unavailability() -> None:
    result = extract_path(FIXTURE_DIR / "09_unavailable_url.json")
    assert result.observations == ()
    assert result.unavailabilities
    assert all(item.recorded_as == "unavailable" for item in result.unavailabilities)
    assert all(item.http_status == 404 for item in result.unavailabilities)


def test_insufficient_text_does_not_invent_fields() -> None:
    result = extract_path(FIXTURE_DIR / "11_insufficient_text.txt")
    assert result.observations == ()
    assert any(item.code == "insufficient_evidence" for item in result.rejections)


def test_replay_is_idempotent(tmp_path) -> None:
    first = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json")
    second = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json")
    assert [item.observation_id for item in first.observations] == [item.observation_id for item in second.observations]
    assert first.observations[0].semantic_dict() == second.observations[0].semantic_dict()
    store = tmp_path / "store.jsonl"
    kept_a, hash_a = append_observations(store, first.observations)
    kept_b, hash_b = append_observations(store, second.observations)
    assert len(kept_a) == 1
    assert len(kept_b) == 1
    assert hash_a == hash_b


def test_different_document_hash_is_new_observation() -> None:
    base = extract_path(FIXTURE_DIR / "01_global_unknown_unit.json").observations[0].as_dict()
    other = dict(base)
    other.pop("observation_id")
    other["source_document_sha256"] = "b" * 64
    other["source_document_id"] = "doc-global-unknown-unit-v2"
    result = extract_payload([base, other])
    assert len(result.observations) == 2
    ids = {item.observation_id for item in result.observations}
    assert len(ids) == 2
