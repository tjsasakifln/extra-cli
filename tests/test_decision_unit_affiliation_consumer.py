"""Fresh consumer of the shipped corroboration entry — not the unit-test file."""

from __future__ import annotations

from scripts.decision_unit_intelligence.affiliation_consumer import evaluate_representative_cases
from scripts.decision_unit_intelligence.affiliation_policy import AffiliationReasonCode
from scripts.decision_unit_intelligence.corroboration import corroborate_affiliation, email_association_gate


def test_consumer_five_cases_return_field_confidences_and_vocabulary():
    first = evaluate_representative_cases()
    second = evaluate_representative_cases()
    assert first == second

    diretor = first["cases"]["diretor_two_independent"]
    for field in (
        "identity_confidence",
        "affiliation_confidence",
        "role_confidence",
        "recency_confidence",
    ):
        assert diretor[field] in {"HIGH", "MEDIUM", "LOW", "UNKNOWN", "NONE"}
    assert AffiliationReasonCode.IDENTITY_CORROBORATED.value in diretor["reason_codes"]
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value in diretor["reason_codes"]
    assert AffiliationReasonCode.ROLE_CORROBORATED.value in diretor["reason_codes"]
    assert diretor["gate"]["allowed"] is True
    assert diretor["gate"]["promotes_email"] is False

    conflict = first["cases"]["conflicting_roles"]
    assert AffiliationReasonCode.CONFLICTING_EVIDENCE.value in conflict["reason_codes"]
    assert AffiliationReasonCode.CONFLICTING_ROLE.value in conflict["reason_codes"]
    assert conflict["role_confidence"] != "HIGH"
    assert conflict["gate"]["allowed"] is False

    qsa = first["cases"]["qsa_only_socio"]
    assert AffiliationReasonCode.QSA_ONLY.value in qsa["reason_codes"]
    assert qsa["gate"]["allowed"] is False
    assert qsa["gate"]["stop_the_line"] is True

    stale = first["cases"]["ex_diretor_nova_empresa"]
    assert (
        AffiliationReasonCode.STALE_AFFILIATION.value in stale["reason_codes"]
        or AffiliationReasonCode.INSUFFICIENT_RECENCY.value in stale["reason_codes"]
    )
    assert stale["gate"]["allowed"] is False

    homonym = first["cases"]["homonym_other_company"]
    assert homonym["company_cnpj"] == "11111111000191"
    assert AffiliationReasonCode.AFFILIATION_CORROBORATED.value not in homonym["reason_codes"]
    assert homonym["gate"]["allowed"] is False


def test_consumer_imports_shipped_entry_not_a_copy():
    assert corroborate_affiliation.__module__ == "scripts.decision_unit_intelligence.corroboration"
    assert email_association_gate.__module__ == "scripts.decision_unit_intelligence.corroboration"
    assert evaluate_representative_cases.__module__ == "scripts.decision_unit_intelligence.affiliation_consumer"
