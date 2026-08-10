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
    TIER_OUT_OF_SCOPE,
    TIER_RESEARCH_ONLY,
    classify_target_fit_send_tier,
    evaluate_copy_context_ready,
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
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 4,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "service_code": "REAJUSTE_14133",
        "portfolio": {"pass_contract_count": 4},
        "factual_hook": "Contrato de engenharia PASS recente no órgão X.",
        "observed_fact": (
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. X; UF RS"
        ),
        "why_this_account": (
            "executora de pavimentação com contratos públicos recentes no RS — "
            "objeto: pavimentação asfáltica CBUQ em vias urbanas"
        ),
        "why_now": "aditivo recente no contrato municipal de pavimentação asfáltica CBUQ",
        "micro_offer_code": "REAJUSTE_CHECK",
        "evidence_ids": ["ev-contract-1"],
        "cta": "Posso te mandar o recorte público que encontrei?",
        "canonical_universe_member": True,
        "service_candidates": [
            {
                "service_id": "estruturacao_pleito_reajuste",
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": ["ev-contract-1"],
            }
        ],
        "primary_service": {
            "service_id": "estruturacao_pleito_reajuste",
            "supporting_signal_ids": ["mature_no_reajuste"],
            "evidence_ids": ["ev-contract-1"],
        },
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
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        source_type="site",
        source_url="https://empresa-target.com.br/contato",
    )
    assert r.email_send_ready is True
    assert r.mailbox_purpose == PURPOSE_GENERIC_CONTACT
    assert r.copy_context_ready is True
    assert r.service_fit_supported is True
    assert r.provenance_chain_valid is True


def test_comercial_preferred_over_generic_rank() -> None:
    g = classify_mailbox_purpose("contato@empresa-target.com.br")
    c = classify_mailbox_purpose("comercial@empresa-target.com.br")
    assert c.purpose == PURPOSE_COMERCIAL
    assert c.rank < g.rank


def _send_ready_company(
    *,
    razao_social: str,
    official_domain: str | None = None,
) -> dict:
    """Minimal company that would pass target/service/copy gates if contact is valid."""
    # Brand token from razao for non-hollow copy (must appear in why_you/why_now).
    brand = next(
        (
            t
            for t in razao_social.replace(",", " ").split()
            if len(t) >= 4
            and t.upper()
            not in {
                "LTDA",
                "EIRELI",
                "ENGENHARIA",
                "CONSTRUTORA",
                "CONSTRUÇÕES",
                "CONSTRUCOES",
                "SERVICOS",
                "OBRAS",
            }
        ),
        razao_social.split()[0],
    )
    row = {
        "razao_social": razao_social,
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 4,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "service_code": "estruturacao_pleito_reajuste",
        "portfolio": {"pass_contract_count": 4},
        "factual_hook": "Contrato de engenharia PASS recente no órgão X.",
        "observed_fact": (
            f"objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha; "
            f"empresa: {brand}; UF RS"
        ),
        "why_this_account": (
            f"{brand} com execução pública de pavimentação — "
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
        ),
        "why_now": (
            f"aditivo recente no contrato de {brand} de pavimentação asfáltica CBUQ "
            "com a Pref. Coxilha"
        ),
        "micro_offer_code": "REAJUSTE_CHECK",
        "evidence_ids": ["ev-contract-1"],
        "cta": "Posso te mandar o recorte público que encontrei?",
        "canonical_universe_member": True,
        "service_candidates": [
            {
                "service_id": "estruturacao_pleito_reajuste",
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": ["ev-contract-1"],
            }
        ],
        "primary_service": {
            "service_id": "estruturacao_pleito_reajuste",
            "supporting_signal_ids": ["mature_no_reajuste"],
            "evidence_ids": ["ev-contract-1"],
        },
    }
    if official_domain:
        row["official_domain"] = official_domain
    return row


def test_sticky_company_owned_wrong_domain_never_email_send_ready() -> None:
    """Sticky COMPANY_OWNED+VERIFIED cannot wash domain↔company identity mismatch.

    Skeptic clean-cohort false WRONG_CONTACT=0 cases must fail at send-ready even
    when feed labels claim COMPANY_OWNED / REAL_OFFICIAL_SITE.
    """
    cases = (
        (
            "contato@qualidademineracao.com.br",
            "QUALIDADE CONSTRUÇÕES E PAVIMENTAÇÕES LTDA",
        ),
        (
            "info@emkoelektronik.com",
            "EMKO CONSTRUTORA LTDA",
        ),
        (
            "comercial@lcmprojetos.com.br",
            "LS ENGENHARIA LTDA",
        ),
        (
            "arantes@terraplenagem.com",
            "JR CONSTRUÇÕES E TERRAPLENAGEM LTDA EPP",
        ),
    )
    for email, razao in cases:
        domain = email.split("@", 1)[1]
        company = _send_ready_company(razao_social=razao, official_domain=domain)
        r = evaluate_email_send_ready(
            company=company,
            email=email,
            ownership_status="COMPANY_OWNED",
            verification_status="VERIFIED",
            service_code="estruturacao_pleito_reajuste",
            factual_evidence=True,
            evidence_ids=["ev-contract-1"],
            source_type="site",
            source_url=f"https://{domain}/contato",
        )
        assert r.email_send_ready is False, (email, r.reasons)
        assert r.contact_send_ready is False, (email, r.reasons)
        assert any("ownership_identity_domain_mismatch" in x for x in r.reasons), r.reasons
        assert any("sticky_ownership_insufficient_for_identity" in x for x in r.reasons)


def test_aligned_company_domain_still_email_send_ready() -> None:
    """Positive control: residual-safe brand domain + sticky COMPANY_OWNED still passes."""
    company = _send_ready_company(
        razao_social="ENCOPAV ENGENHARIA LTDA",
        official_domain="encopav.com.br",
    )
    r = evaluate_email_send_ready(
        company=company,
        email="encopav@encopav.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        source_type="site",
        source_url="https://encopav.com.br/contato",
    )
    assert r.email_send_ready is True, r.reasons
    assert r.contact_send_ready is True
    assert "domain_aligned_with_company" in r.reasons


def test_eshop_mailbox_blocked_even_if_domain_matches() -> None:
    """Retail eshop@ is never commercial autorun (BARRA NOVA / eshop@barranova)."""
    mp = classify_mailbox_purpose("eshop@barranova.com")
    assert mp.send_blocked is True
    company = _send_ready_company(
        razao_social="BARRA NOVA ENGENHARIA LTDA",
        official_domain="barranova.com",
    )
    r = evaluate_email_send_ready(
        company=company,
        email="eshop@barranova.com",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        source_type="site",
        source_url="https://barranova.com/contato",
    )
    assert r.email_send_ready is False
    assert r.contact_send_ready is False


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


def test_possible_fit_never_send_tier_even_with_pass_counts() -> None:
    """POSSIBLE is TARGET_PROBABLE_RESEARCH — never EMAIL_SEND_READY tier A/B."""
    company = {
        "construction_evidence": {
            "sector_fit": "POSSIBLE_ENGINEERING_FIT",
            "target_fit_class": "TARGET_PROBABLE_RESEARCH",
            "relevant_contract_count": 3,
        },
        "target_fit_class": "TARGET_PROBABLE_RESEARCH",
        "portfolio": {"pass_contract_count": 3},
        "service_code": "REAJUSTE_14133",
        "primary_trigger": "NEW_RELEVANT_CONTRACT",
        "factual_hook": "3 contratos PASS",
        "canonical_universe_member": True,
    }
    fit = classify_target_fit_send_tier(company)
    assert fit.tier == TIER_RESEARCH_ONLY
    r = evaluate_email_send_ready(
        company=company,
        email="comercial@x.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="REAJUSTE_14133",
        factual_evidence=True,
    )
    assert r.email_send_ready is False


def test_a_automatic_confirmed() -> None:
    company = {
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 2,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "portfolio": {"pass_contract_count": 2},
        "factual_hook": "obra pública",
        "canonical_universe_member": True,
    }
    assert classify_target_fit_send_tier(company).tier == TIER_A_AUTOMATIC


def test_ready_supply_target_formula() -> None:
    # 20/h × 9h × 2 days = 360
    assert ready_supply_target(max_send_rate=20, send_window_hours=9, ready_supply_target_days=2) == 360


def test_send_ready_invariant_requires_universe_and_tier() -> None:
    """SEND_READY => canonical_universe_member && tier in {A,B}."""
    company = {
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
        },
        "target_fit_class": "TARGET_CONFIRMED",
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


def test_copy_context_incomplete_blocks_send_ready() -> None:
    company = {
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 3,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "service_code": "gestao_monitoramento_contratual",
        "portfolio": {"pass_contract_count": 3},
        "canonical_universe_member": True,
        # missing why_you / micro_offer / evidence / cta on purpose
        "factual_hook": "portfólio público",
    }
    r = evaluate_email_send_ready(
        company=company,
        email="comercial@construtora.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="gestao_monitoramento_contratual",
        factual_evidence=True,
    )
    assert r.email_send_ready is False
    assert r.copy_context_ready is False
    assert any("copy_context" in x for x in r.reasons)


def test_total_contract_count_is_not_pass_evidence() -> None:
    """Regression: active_contract_count must not inflate pass_contract_count."""
    company = {
        "construction_evidence": {"sector_fit": "POSSIBLE_ENGINEERING_FIT"},
        "portfolio": {"active_contract_count": 69, "contract_count_total": 69},
        "canonical_universe_member": True,
    }
    fit = classify_target_fit_send_tier(company)
    assert fit.tier == TIER_RESEARCH_ONLY


def test_evaluate_copy_context_requires_non_generic_why() -> None:
    company = {
        "why_this_account": "empresa com momento comercial público: ACME",
        "why_now": "x",
        "observed_fact": "y",
        "service_code": "REAJUSTE",
        "micro_offer_code": "REAJUSTE_CHECK",
        "evidence_ids": ["e1"],
        "cta": "posso enviar?",
    }
    res = evaluate_copy_context_ready(company)
    assert res.copy_context_ready is False
    assert "why_this_account" in res.missing_fields


def test_copy_context_rejects_hollow_portfolio_count_fact() -> None:
    """COPY_CONTEXT must reject portfolio-count as observed_fact (skeptic gap)."""
    company = {
        "why_this_account": (
            "ACME com execução pública observável — objeto: pavimentação asfáltica "
            "CBUQ no município de Coxilha; órgão: Pref. Coxilha"
        ),
        "why_now": "Menção a reequilíbrio em material contratual ingerido com nexo documentado.",
        "observed_fact": "Portfólio público observado com 3 contrato(s) no input.",
        "service_code": "REEQUILIBRIO",
        "micro_offer_code": "CLAIM_READINESS_CHECK",
        "evidence_ids": ["cf-portfolio-count"],
        "cta": "Ofereço leitura técnica do material de reequilíbrio.",
    }
    res = evaluate_copy_context_ready(company)
    assert res.copy_context_ready is False
    assert "observed_fact" in res.missing_fields


def test_service_fit_requires_candidate_evidence_not_bare_code() -> None:
    """Bare service_code without signals/evidence is NOT SERVICE_FIT_SUPPORTED."""
    company = {
        "outreach_eligibility": "ELIGIBLE",
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": "TARGET_CONFIRMED",
            "relevant_contract_count": 3,
        },
        "target_fit_class": "TARGET_CONFIRMED",
        "service_code": "auditoria_orcamento_bdi",
        "canonical_universe_member": True,
        "observed_fact": "objeto: pavimentação asfáltica em CBUQ; órgão: Pref. Y",
        "why_this_account": "ACME — objeto: pavimentação asfáltica em CBUQ; órgão: Pref. Y",
        "why_now": "Portfólio multi-contrato sem especialidade documental de planilha.",
        "micro_offer_code": "DOCUMENT_CHECKLIST",
        "evidence_ids": ["cf-contract-1"],
        "cta": "Posso enviar checklist de planilha?",
        # no service_candidates / supporting_signal_ids
    }
    r = evaluate_email_send_ready(
        company=company,
        email="comercial@construtora.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="auditoria_orcamento_bdi",
        factual_evidence=True,
        evidence_ids=["cf-contract-1"],
    )
    assert r.service_fit_supported is False
    assert r.email_send_ready is False
    assert any("service_fit_unsupported" in x for x in r.reasons)
