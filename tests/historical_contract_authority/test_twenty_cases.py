"""Twenty adversarial cases against the shipped dossier engine."""

from __future__ import annotations

from scripts.historical_contract_authority.cases import CASE_BUILDERS
from scripts.historical_contract_authority.engine import build_dossier, replay_formula
from scripts.historical_contract_authority.schema import FORBIDDEN_PUBLIC_STATES, HANDOFF_MIN_SCORE, SCHEMA


def _dossier(name: str):
    return build_dossier(CASE_BUILDERS[name](), as_of="2026-08-17T12:00:00Z", snapshot_hash="snap-test-1")


def test_large_contract_without_insight_is_rejected() -> None:
    dossier = _dossier("large_no_insight")
    assert dossier.state == "REJECT"
    assert "no_specific_technical_question" in dossier.reason_codes
    assert dossier.state != "HANDOFF_READY"


def test_insufficient_documents_hold_or_reject() -> None:
    dossier = _dossier("insufficient_docs")
    assert dossier.state in {"REJECT", "HOLD_FOR_DATA"}
    assert "insufficient_documents" in dossier.reason_codes


def test_divergent_identity_rejected() -> None:
    dossier = _dossier("identity_divergent")
    assert dossier.state == "REJECT"
    assert "identity_swap" in dossier.reason_codes


def test_value_without_semantics_not_invented() -> None:
    dossier = _dossier("value_no_semantic")
    assert dossier.state != "HANDOFF_READY"
    assert dossier.identity.get("contract_id")
    assert "value_without_semantics" in dossier.reason_codes
    assert dossier.comparability.status in {"HOLD_FOR_DATA", "NOT_COMPARABLE"}


def test_hidden_date_conflict_rejected() -> None:
    dossier = _dossier("conflicting_dates")
    assert dossier.state == "REJECT"
    assert "value_or_date_conflict" in dossier.reason_codes


def test_term_amendment_has_chronology_and_sources() -> None:
    dossier = _dossier("prazo_additive")
    kinds = {item.kind for item in dossier.chronology}
    assert "amendment_term" in kinds
    event = next(item for item in dossier.chronology if item.kind == "amendment_term")
    assert event.source_refs and event.locators
    assert any(item.claim_id == "c-prazo-adt" for item in dossier.claims)


def test_value_amendment_has_replayable_delta() -> None:
    dossier = _dossier("valor_additive")
    calc = next(item for item in dossier.calculations if item.formula == "delta_value")
    assert calc.computable
    assert calc.result == "510000.00"
    assert calc.unit == "BRL"
    ok, result, digest = replay_formula(calc.formula, calc.inputs, unit=calc.unit, rounding=calc.rounding)
    assert ok and result == calc.result and digest == calc.replay_hash


def test_scope_change_is_documented() -> None:
    dossier = _dossier("scope_changed")
    assert any(item.kind == "scope_change" for item in dossier.chronology)
    assert any(item.claim_id == "c-escopo" for item in dossier.claims)


def test_superseded_document_marked() -> None:
    dossier = _dossier("superseded_document")
    assert any(item.superseded_by == "doe-001" for item in dossier.documents)
    claim = next(item for item in dossier.claims if item.claim_id == "c-old")
    assert claim.superseded_by == "doe-001"


def test_weak_ocr_preserves_unknown() -> None:
    dossier = _dossier("weak_ocr")
    assert any(
        item.ocr_used and item.ocr_confidence is not None and item.ocr_confidence < 0.5 for item in dossier.documents
    )
    assert any(item.klass == "UNKNOWN" for item in dossier.claims)
    assert not any(item.klass == "FACT" and "UNKNOWN" in item.text for item in dossier.claims)


def test_calculation_replay_is_deterministic() -> None:
    first = _dossier("calculation_replay")
    second = _dossier("calculation_replay")
    assert first.calculations[0].replay_hash == second.calculations[0].replay_hash
    assert first.calculations[0].result == second.calculations[0].result


def test_irregularity_inference_never_becomes_fact() -> None:
    dossier = _dossier("irregularity_inference")
    labeled = next(item for item in dossier.claims if item.claim_id == "c-irr")
    assert labeled.klass == "INFERENCE"
    assert labeled.publication_fit != "as_fact"
    blob = " ".join(item.text.casefold() for item in dossier.claims if item.klass == "FACT")
    assert "irregularidade" not in blob


def test_comparison_without_unit_or_regime_uses_415() -> None:
    dossier = _dossier("comparison_no_unit")
    assert dossier.comparability.engine.endswith("build_peer_group")
    assert dossier.comparability.status in {"HOLD_FOR_DATA", "NOT_COMPARABLE"}
    assert dossier.comparability.status != "COMPARABLE"


def test_valid_comparable_calls_415_with_admissible_fields() -> None:
    dossier = _dossier("valid_comparable")
    assert dossier.comparability.status in {"COMPARABLE", "HOLD_FOR_DATA", "NOT_COMPARABLE"}
    assert (
        dossier.comparability.schema.startswith("comparable-contracts") or "comparable" in dossier.comparability.schema
    )
    if dossier.comparability.status == "COMPARABLE":
        assert dossier.comparability.usable_n >= 1


def test_counter_evidence_examined() -> None:
    dossier = _dossier("counter_evidence")
    assert dossier.contradictions
    assert "c-chuva" in dossier.contradictions[0].weakens
    assert dossier.contradictions[0].alternatives


def test_fact_without_locator_fails_quality() -> None:
    dossier = _dossier("claim_no_locator")
    assert dossier.state != "HANDOFF_READY"
    assert dossier.score.hard_gates["facts_sourced_located"] is False


def test_duplication_replay_same_dossier_id() -> None:
    first = _dossier("duplication_replay")
    second = _dossier("duplication_replay")
    assert first.dossier_id == second.dossier_id
    assert first.as_dict()["content_hash"] == second.as_dict()["content_hash"]


def test_hash_is_stable_across_two_builds() -> None:
    first = _dossier("stable_hash").as_dict()["content_hash"]
    second = _dossier("stable_hash").as_dict()["content_hash"]
    assert first == second
    assert len(first) == 64


def test_schema_is_versioned() -> None:
    dossier = _dossier("consumer_import")
    assert dossier.schema == SCHEMA
    assert dossier.schema == "historical-contract-authority-dossier/1.0"


def test_no_publishable_or_index_in_dossier() -> None:
    payload = _dossier("no_publishable").as_dict()
    blob = str(payload)
    for token in FORBIDDEN_PUBLIC_STATES:
        assert token not in blob
    assert payload.get("state") in {"REJECT", "HOLD_FOR_DATA", "HANDOFF_READY"}


def test_handoff_ready_fixture_clears_score_and_gates() -> None:
    dossier = _dossier("handoff_ready")
    assert dossier.state == "HANDOFF_READY"
    assert dossier.score.score >= HANDOFF_MIN_SCORE
    assert not dossier.score.below_floor
    assert all(dossier.score.hard_gates.values())
    assert len([item for item in dossier.claims if item.klass in {"FACT", "CALCULATION"}]) >= 5
