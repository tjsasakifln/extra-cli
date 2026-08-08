"""Audit regressions: mailbox purpose + EMAIL_SEND_READY (EMAIL_ONLY)."""

from __future__ import annotations

from scripts.confenge_contact_resolution.mailbox_purpose import (
    PURPOSE_COMERCIAL,
    PURPOSE_GENERIC_CONTACT,
    PURPOSE_HR_RECRUITING,
    classify_mailbox_purpose,
    is_mailbox_send_allowed,
)
from scripts.confenge_contact_resolution.send_readiness import (
    TIER_A_AUTOMATIC,
    TIER_B_EVIDENCE_SUPPORTED,
    TIER_OUT_OF_SCOPE,
    TIER_RESEARCH_ONLY,
    classify_target_fit_send_tier,
    evaluate_email_send_ready,
    ready_supply_target,
)


def test_vagas_may_be_owned_but_not_email_send_ready() -> None:
    """vagas@moveinfraestrutura.com.br → purpose HR; EMAIL_SEND_READY=false."""
    email = "vagas@moveinfraestrutura.com.br"
    mp = classify_mailbox_purpose(email)
    assert mp.purpose == PURPOSE_HR_RECRUITING
    assert mp.send_blocked is True
    assert is_mailbox_send_allowed(email) is False

    company = {
        "cnpj14": "12345678000199",
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {"sector_fit": "CONFIRMED_ENGINEERING"},
        "service_code": "REAJUSTE_14133",
        "portfolio": {"pass_contract_count": 5},
        "factual_hook": "Contrato PNCP recente de obra pública.",
        "canonical_universe_member": True,
    }
    r = evaluate_email_send_ready(
        company=company,
        email=email,
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        dnc=False,
        bounce=False,
        service_code="REAJUSTE_14133",
        factual_evidence=True,
    )
    assert r.ownership_status == "COMPANY_OWNED"
    assert r.mailbox_purpose == PURPOSE_HR_RECRUITING
    assert r.email_send_ready is False
    assert any("mailbox_purpose" in x or "HR" in x for x in r.reasons)


def test_phone_only_never_email_send_ready() -> None:
    company = {
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {"sector_fit": "CONFIRMED_ENGINEERING"},
        "service_code": "REAJUSTE_14133",
        "factual_hook": "x",
        "canonical_universe_member": True,
        "portfolio": {"pass_contract_count": 3},
    }
    r = evaluate_email_send_ready(
        company=company,
        email=None,
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="REAJUSTE_14133",
        factual_evidence=True,
    )
    assert r.email_send_ready is False
    assert "no_email" in r.reasons


def test_out_of_scope_verified_email_not_send_ready() -> None:
    company = {
        "outreach_eligibility": "NOT_CONSTRUCTION",
        "construction_evidence": {"sector_fit": "OUT_OF_SCOPE"},
        "service_code": "REAJUSTE_14133",
        "canonical_universe_member": True,
        "factual_hook": "x",
    }
    r = evaluate_email_send_ready(
        company=company,
        email="contato@farmacia-exemplo.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="REAJUSTE_14133",
        factual_evidence=True,
    )
    assert r.target_fit_send_tier == TIER_OUT_OF_SCOPE
    assert r.email_send_ready is False


def test_generic_contato_can_pass_when_all_gates_ok() -> None:
    company = {
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {"sector_fit": "CONFIRMED_ENGINEERING"},
        "service_code": "REAJUSTE_14133",
        "portfolio": {"pass_contract_count": 4},
        "factual_hook": "Contrato de engenharia PASS recente.",
        "canonical_universe_member": True,
    }
    email = "contato@empresa-target.com.br"
    mp = classify_mailbox_purpose(email)
    assert mp.purpose == PURPOSE_GENERIC_CONTACT
    assert mp.send_blocked is False
    r = evaluate_email_send_ready(
        company=company,
        email=email,
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="REAJUSTE_14133",
        factual_evidence=True,
    )
    assert r.email_send_ready is True
    assert r.mailbox_purpose == PURPOSE_GENERIC_CONTACT


def test_comercial_preferred_over_generic_rank() -> None:
    g = classify_mailbox_purpose("contato@empresa-target.com.br")
    c = classify_mailbox_purpose("comercial@empresa-target.com.br")
    assert c.purpose == PURPOSE_COMERCIAL
    assert c.rank < g.rank


def test_shared_phone_not_company_owned_autorun() -> None:
    """Ownership gate: shared external must not be EMAIL_SEND_READY."""
    company = {
        "construction_evidence": {"sector_fit": "CONFIRMED_ENGINEERING"},
        "service_code": "X",
        "canonical_universe_member": True,
        "factual_hook": "y",
        "portfolio": {"pass_contract_count": 2},
    }
    r = evaluate_email_send_ready(
        company=company,
        email="contato@shared-bpo.com.br",
        ownership_status="SHARED_EXTERNAL_CONTACT",
        verification_status="OBSERVED",
        service_code="X",
        factual_evidence=True,
    )
    assert r.email_send_ready is False
    assert any("ownership" in x for x in r.reasons)


def test_research_only_stays_in_reservoir_not_send_ready() -> None:
    company = {
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {"sector_fit": "POSSIBLE_ENGINEERING_FIT"},
        "portfolio": {"pass_contract_count": 0},
        "canonical_universe_member": True,
    }
    fit = classify_target_fit_send_tier(company)
    assert fit.tier == TIER_RESEARCH_ONLY
    assert fit.canonical_universe_member is True
    r = evaluate_email_send_ready(
        company=company,
        email="engenharia@obra.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="REAJUSTE_14133",
        factual_evidence=True,
    )
    assert r.email_send_ready is False
    assert r.target_fit_send_tier == TIER_RESEARCH_ONLY


def test_b_evidence_supported_possible_with_pass_contracts() -> None:
    company = {
        "construction_evidence": {"sector_fit": "POSSIBLE_ENGINEERING_FIT"},
        "portfolio": {"pass_contract_count": 3},
        "service_code": "REAJUSTE_14133",
        "primary_trigger": "NEW_RELEVANT_CONTRACT",
        "factual_hook": "3 contratos PASS",
        "canonical_universe_member": True,
    }
    fit = classify_target_fit_send_tier(company)
    assert fit.tier == TIER_B_EVIDENCE_SUPPORTED


def test_a_automatic_confirmed() -> None:
    company = {
        "construction_evidence": {"sector_fit": "CONFIRMED_ENGINEERING"},
        "canonical_universe_member": True,
    }
    assert classify_target_fit_send_tier(company).tier == TIER_A_AUTOMATIC


def test_ready_supply_target_formula() -> None:
    # 20/h × 9h × 2 days = 360
    assert ready_supply_target(max_send_rate=20, send_window_hours=9, ready_supply_target_days=2) == 360


def test_send_ready_invariant_requires_universe_and_tier() -> None:
    """SEND_READY => canonical_universe_member && tier in {A,B}."""
    company = {
        "construction_evidence": {"sector_fit": "CONFIRMED_ENGINEERING"},
        "canonical_universe_member": False,
        "service_code": "X",
        "factual_hook": "y",
    }
    r = evaluate_email_send_ready(
        company=company,
        email="comercial@eng.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="X",
        factual_evidence=True,
    )
    assert r.email_send_ready is False
