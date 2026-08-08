"""Golden contrast profiles: five distinct primary services/angles."""

from __future__ import annotations

from scripts.confenge_account_intelligence.pipeline import build_dossier
from scripts.confenge_account_intelligence.schema import validate_dossier


def test_five_golden_profiles_differ(
    regional_lean: dict,
    national_structured: dict,
    addendum_signals: dict,
    mature_no_reajuste: dict,
    insufficient_facts: dict,
) -> None:
    cases = {
        "regional_lean": regional_lean,
        "national_structured": national_structured,
        "addendum_signals": addendum_signals,
        "mature_no_reajuste": mature_no_reajuste,
        "insufficient_facts": insufficient_facts,
    }
    dossiers = {name: build_dossier(raw) for name, raw in cases.items()}

    for name, d in dossiers.items():
        errors = validate_dossier(d)
        assert not errors, f"{name}: {errors}"
        assert d["schema_id"] == "confenge-account-intelligence-v1"
        assert d["primary_service"]["service_id"]
        assert d["internal_structure_hypothesis"]["assertion_as_fact"] is False

    primaries = {name: d["primary_service"]["service_id"] for name, d in dossiers.items()}

    # Expected routing (evidence + moment, not score template)
    assert primaries["regional_lean"] == "reforco_temporario_backoffice"
    assert primaries["national_structured"] == "auditoria_orcamento_bdi"
    assert primaries["addendum_signals"] == "aditivos_extracontratuais"
    assert primaries["mature_no_reajuste"] == "estruturacao_pleito_reajuste"
    assert primaries["insufficient_facts"] == "diagnostico_contratual_b2g"

    # All five primary services must be pairwise distinct
    assert len(set(primaries.values())) == 5, primaries

    # Approach angles also differ (CTA / framing)
    ctas = {name: d["cta"] for name, d in dossiers.items()}
    assert len(set(ctas.values())) == 5

    # Robust never framed as no-structure outsource
    nat = dossiers["national_structured"]
    assert nat["internal_structure_hypothesis"]["structure_class"] == "robust"
    framing = nat["message_tone"]["framing"].lower()
    assert "não tem estrutura" not in framing
    assert "sem estrutura" not in framing
    claims = " ".join(nat["claims_to_avoid"]).lower()
    assert "não tem estrutura" in claims or "outsourcing pleno" in claims

    # Insufficient → discovery path, not fabricated specialty
    insuff = dossiers["insufficient_facts"]
    assert insuff["primary_service"]["service_id"] == "diagnostico_contratual_b2g"
    assert insuff["why_now"]["trigger"] == "insufficient_facts"
    assert any("insuficient" in g.lower() or "contrato" in g.lower() for g in insuff["research_gaps"])


def test_epistemic_separation_and_evidence_ids(addendum_signals: dict) -> None:
    d = build_dossier(addendum_signals)
    for item in d["confirmed_facts"]:
        assert item["epistemic_class"] == "confirmed"
        assert "evidence_ids" in item
        assert "provenance" in item
        assert 0 <= item["confidence"] <= 1
    for item in d["strong_inferences"] + d["weak_inferences"]:
        assert item["epistemic_class"] in {"strong_inference", "weak_inference"}
        assert item["epistemic_class"] != "confirmed"
    # Inference must not appear inside confirmed_facts by id prefix convention
    conf_ids = {i["id"] for i in d["confirmed_facts"]}
    for item in d["strong_inferences"] + d["weak_inferences"]:
        assert item["id"] not in conf_ids or item["epistemic_class"] != "confirmed"


def test_absence_is_not_lean_proof(insufficient_facts: dict) -> None:
    d = build_dossier(insufficient_facts)
    hyp = d["internal_structure_hypothesis"]
    # No contracts + empty signals → unknown, not lean
    assert hyp["structure_class"] == "unknown"
    assert hyp["assertion_as_fact"] is False
    notes = hyp["notes"].lower()
    assert "não prova" in notes or "ausência" in notes


def test_cache_stable(regional_lean: dict, tmp_path) -> None:
    d1 = build_dossier(regional_lean, use_cache=True, cache_dir=tmp_path)
    d2 = build_dossier(regional_lean, use_cache=True, cache_dir=tmp_path)
    assert d2.get("cache_hit") is True
    assert d1["cache_key"] == d2["cache_key"]
    assert d1["primary_service"]["service_id"] == d2["primary_service"]["service_id"]
    assert d1["source_hash"] == d2["source_hash"]
    # Deterministic routing fields
    assert d1["service_fit_rationale"] == d2["service_fit_rationale"]
