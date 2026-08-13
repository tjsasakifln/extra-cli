"""Permanent adversarial regressions: provenance taint never becomes EMAIL_SEND_READY.

Covers:
  - fixture marked VERIFIED cannot send
  - demo marked COMPANY_OWNED cannot send
  - synthetic marked HUMAN_CONFIRMED cannot send
  - derived cached candidate inherits taint
  - export/mapping blocks tainted candidate
  - official-company email with real provenance can send
  - machine process cannot mint HUMAN_REVIEW_APPROVED
  - sticky VERIFIED does not override live tainted store
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.confenge_contact_resolution.human_review import (
    HUMAN_REVIEW_APPROVED,
    MACHINE_REVIEW_PASS,
    is_forbidden_reviewer,
    machine_review_status,
    mint_human_review_decision,
)
from scripts.confenge_contact_resolution.provenance_trust import (
    ProvenanceTrust,
    RootSourceType,
    evaluate_contact_provenance,
    evaluate_provenance_trust,
    is_demo_or_fixture_email,
)
from scripts.confenge_contact_resolution.send_readiness import (
    UNSUITABLE_PROVENANCE,
    evaluate_email_send_ready,
)
from scripts.warmbly_bridge.mapping import build_leads


def _good_company(**overrides: object) -> dict:
    base = {
        "razao_social": "EMPRESA TARGET PAVIMENTACAO LTDA",
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
        "observed_fact": ("objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha; UF RS"),
        "why_this_account": (
            "EMPRESA TARGET com execução pública de pavimentação — "
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
        ),
        "why_now": (
            "aditivo recente no contrato municipal de EMPRESA TARGET de pavimentação asfáltica CBUQ com a Pref. Coxilha"
        ),
        "micro_offer_code": "REAJUSTE_CHECK",
        "evidence_ids": ["ev-contract-1"],
        "cta": "Posso te mandar o recorte público que encontrei?",
        "canonical_universe_member": True,
        "official_domain": "empresa-target.com.br",
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
    base.update(overrides)
    return base


def _eval(
    email: str,
    *,
    ownership: str = "COMPANY_OWNED",
    verification: str = "VERIFIED",
    **kwargs: object,
):
    return evaluate_email_send_ready(
        company=_good_company(),
        email=email,
        ownership_status=ownership,
        verification_status=verification,
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        **kwargs,  # type: ignore[arg-type]
    )


# ── demo / fixture / synthetic never send ───────────────────────────────────


def test_demo_email_company_owned_verified_not_send_ready() -> None:
    """licitacoes@demo00Xobra.com.br must never be EMAIL_SEND_READY."""
    for i in range(10):
        email = f"licitacoes@demo{i:03d}obra.com.br"
        assert is_demo_or_fixture_email(email)
        r = _eval(
            email,
            ownership="COMPANY_OWNED",
            verification="VERIFIED",
            source_type="site",
            source_url=f"https://demo{i:03d}obra.com.br/contato",
        )
        assert r.email_send_ready is False, email
        assert r.provenance_chain_valid is False
        assert r.derived_from_fixture or r.root_source_type in {
            RootSourceType.DEMO.value,
            RootSourceType.TEST_FIXTURE.value,
        }
        assert r.recipient_commercial_suitability == UNSUITABLE_PROVENANCE
        assert any("provenance" in x or "taint" in x or "demo" in x for x in r.reasons)


def test_fixture_marked_verified_cannot_send() -> None:
    r = _eval(
        "contato@construtora-real.com.br",
        ownership="COMPANY_OWNED",
        verification="VERIFIED",
        source_type="fixture",
        source_url="https://fixtures.local/contato",
        fixtures_dir_used=True,
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False
    assert r.derived_from_fixture is True
    assert r.root_source_type == RootSourceType.TEST_FIXTURE.value


def test_synthetic_human_confirmed_cannot_send() -> None:
    r = _eval(
        "diretor@acme-engenharia.com.br",
        ownership="HUMAN_CONFIRMED",
        verification="HUMAN_CONFIRMED",
        synthetic_flag=True,
        source_type="synthetic",
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False
    assert r.root_source_type == RootSourceType.SYNTHETIC.value


def test_demo_at_example_cannot_send() -> None:
    r = _eval(
        "demo@example.com",
        ownership="COMPANY_OWNED",
        verification="VERIFIED",
        source_type="site",
        source_url="https://example.com/contact",
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False


def test_derived_cached_candidate_inherits_taint() -> None:
    """fixture → candidate → cache → prior verified → still tainted."""
    parent = evaluate_provenance_trust(
        email="licitacoes@demo001obra.com.br",
        source_type="site",
        source_url="https://demo001obra.com.br/contato",
        verification_status="VERIFIED",
        ownership_status="COMPANY_OWNED",
    ).as_dict()
    assert parent["provenance_chain_valid"] is False

    r = _eval(
        "licitacoes@demo001obra.com.br",
        ownership="COMPANY_OWNED",
        verification="VERIFIED",
        source_type="prior_verified_candidate",
        parent_provenance=parent,
        provenance_chain=[
            {
                "stage": "fixture",
                "source_type": "fixture",
                "root_source_type": RootSourceType.TEST_FIXTURE.value,
                "tainted": True,
            },
            {
                "stage": "contacts_verified.jsonl",
                "source_type": "site",
                "root_source_type": RootSourceType.DEMO.value,
                "tainted": True,
            },
            {
                "stage": "cache",
                "source_type": "cached_candidate",
                "tainted": True,
            },
        ],
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False


def test_fixture_derived_real_looking_domain_still_tainted() -> None:
    """Fixture path that yields a real-looking domain remains blocked by provenance."""
    r = _eval(
        "contato@construtora-alpha.com.br",
        ownership="COMPANY_OWNED",
        verification="VERIFIED",
        contact={
            "email": "contato@construtora-alpha.com.br",
            "ownership_status": "COMPANY_OWNED",
            "verification_status": "VERIFIED",
            "source": {
                "source_type": "site",
                "source_url": "https://construtora-alpha.com.br/contato",
                "notes": "loaded from fixture suite (test only)",
            },
            "fixtures_dir_used": True,
            "derived_from_fixture": True,
        },
    )
    assert r.email_send_ready is False
    assert r.derived_from_fixture is True


def test_stale_embedded_verified_overridden_by_tainted_live_store() -> None:
    """Stale embed saying VERIFIED cannot beat live parent tainted provenance."""
    live_tainted = {
        "provenance_trust": ProvenanceTrust.TAINTED.value,
        "provenance_chain_valid": False,
        "root_source_type": RootSourceType.DEMO.value,
        "root_source_url": "https://demo005obra.com.br",
        "derived_from_fixture": False,
        "derived_from_demo": True,
        "taint_reasons": ["demo_email"],
    }
    r = _eval(
        "licitacoes@demo005obra.com.br",
        ownership="COMPANY_OWNED",
        verification="VERIFIED",  # stale sticky label
        parent_provenance=live_tainted,
        source_type="site",
        source_url="https://demo005obra.com.br/contato",
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False


def test_unknown_provenance_blocks_send() -> None:
    r = _eval(
        "contato@empresa-sem-fonte.com.br",
        ownership="COMPANY_OWNED",
        verification="VERIFIED",
        # no source_type / source_url → UNKNOWN
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False
    assert r.root_source_type == RootSourceType.UNKNOWN.value


# ── real provenance can send ────────────────────────────────────────────────


def test_foreign_provenance_host_blocks_send_ready() -> None:
    """comercial@connector.eng.br with root URL caiafafacilities.com.br must never send.

    Skeptic gap: provenance_chain_valid was true when site host ≠ email domain.
    """
    company = _good_company(
        razao_social="CONNECTOR ENGENHARIA LTDA",
        official_domain="connector.eng.br",
        why_this_account=(
            "CONNECTOR com execução pública de engenharia — objeto: obras de "
            "infraestrutura viária; órgão: Pref. de Florianópolis"
        ),
        why_now=("aditivo recente no contrato de CONNECTOR de infraestrutura viária com a Pref. de Florianópolis"),
        observed_fact=("objeto: obras de infraestrutura viária; órgão: Pref. de Florianópolis; UF SC"),
    )
    r = evaluate_email_send_ready(
        company=company,
        email="comercial@connector.eng.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        source_type="site",
        source_url="https://caiafafacilities.com.br/",
        provenance_chain=[
            {
                "source_type": "site",
                "source_url": "https://caiafafacilities.com.br/",
                "method": "host_enrich_confirmed",
                "observed_at": "2026-08-10T06:03:00Z",
                "root": True,
            }
        ],
        contact={
            "email": "comercial@connector.eng.br",
            "ownership_status": "COMPANY_OWNED",
            "verification_status": "VERIFIED",
            "source_type": "site",
            "source_url": "https://caiafafacilities.com.br/",
            "provenance_chain": [
                {
                    "source_type": "site",
                    "source_url": "https://caiafafacilities.com.br/",
                    "method": "host_enrich_confirmed",
                    "root": True,
                }
            ],
        },
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is False
    assert any("provenance_host_mismatch" in x or "taint" in x or "provenance" in x for x in r.reasons), r.reasons


def test_hollow_identical_template_copy_blocks_send_ready() -> None:
    """Cohort-level identical why_you/why_now templates must fail COPY_CONTEXT."""
    company = _good_company(
        razao_social="ENCOPAV ENGENHARIA LTDA",
        official_domain="encopav.com.br",
        why_this_account=(
            "executora com contratos públicos recentes de engenharia e momento de reajuste/aditivo observável"
        ),
        why_now="aditivo ou medição recente no contrato principal de obra pública",
        observed_fact="objeto: obra de engenharia/pavimentação com execução pública recente",
    )
    r = evaluate_email_send_ready(
        company=company,
        email="encopav@encopav.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-1"],
        source_type="site",
        source_url="https://encopav.com.br/contato",
        provenance_chain=[
            {
                "source_type": "site",
                "source_url": "https://encopav.com.br/contato",
                "method": "site",
                "root": True,
            }
        ],
    )
    assert r.email_send_ready is False
    assert r.copy_context_ready is False
    assert any("copy_context" in x or "why_this_account" in x for x in r.reasons), r.reasons


def test_generic_official_company_email_is_not_a_human_recipient() -> None:
    r = _eval(
        "contato@empresa-target.com.br",
        ownership="COMPANY_OWNED",
        verification="OBSERVED",
        source_type="site",
        source_url="https://empresa-target.com.br/contato",
    )
    assert r.email_send_ready is False
    assert r.provenance_chain_valid is True
    assert r.root_source_type == RootSourceType.REAL_OFFICIAL_SITE.value
    assert r.derived_from_fixture is False


def test_registry_provenance_cannot_infer_a_human_recipient() -> None:
    company = _good_company(
        razao_social="ENGENHARIA BETA OBRAS LTDA",
        official_domain="engenharia-beta.com.br",
        why_this_account=(
            "BETA com execução pública de engenharia — objeto: pavimentação asfáltica "
            "CBUQ; órgão: Pref. de Caxias do Sul"
        ),
        why_now=("aditivo recente no contrato de BETA de pavimentação asfáltica CBUQ com a Pref. de Caxias do Sul"),
        observed_fact=("objeto: pavimentação asfáltica CBUQ; órgão: Pref. de Caxias do Sul; UF RS"),
    )
    r = evaluate_email_send_ready(
        company=company,
        email="comercial@engenharia-beta.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["ev-contract-1"],
        source_type="registry",
        source_url="official_company_registry",
    )
    assert r.email_send_ready is False, r.reasons
    assert "functional_mailbox_not_human_recipient" in r.reasons
    assert r.root_source_type == RootSourceType.REAL_REGISTRY.value


# ── export / mapping boundary ───────────────────────────────────────────────


def test_export_mapping_blocks_tainted_demo_candidate(tmp_path: Path) -> None:
    universe = [
        {
            "cnpj14": "01449930000190",
            "company_name": "SIEMENS HEALTHCARE DIAGNOSTICOS LTDA.",
            "razao_social": "SIEMENS HEALTHCARE DIAGNOSTICOS LTDA.",
            "official_domain": "demo000obra.com.br",
            "outreach_eligibility": "ELIGIBLE",
            "target_fit_class": "TARGET_CONFIRMED",
            "construction_evidence": {
                "sector_fit": "CONFIRMED_ENGINEERING",
                "target_fit_class": "TARGET_CONFIRMED",
                "relevant_contract_count": 3,
            },
            "portfolio": {"pass_contract_count": 3},
            "canonical_universe_member": True,
        }
    ]
    intel = [
        {
            "cnpj14": "01449930000190",
            "why_now": {
                "summary": "aditivo recente no contrato municipal de pavimentação asfáltica CBUQ",
                "temporal_fact": "aditivo recente no contrato municipal de pavimentação asfáltica CBUQ",
                "evidence_ids": ["ev-1"],
            },
            "offer": {
                "service_code": "estruturacao_pleito_reajuste",
                "entry_offer": "REAJUSTE_CHECK",
            },
            "messaging": {
                "why_this_account": (
                    "executora de pavimentação com contratos públicos recentes — objeto: pavimentação asfáltica CBUQ"
                ),
                "fact_to_mention": ("objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. X"),
                "cta": "Posso te mandar o recorte público?",
            },
            "primary_service": {
                "service_id": "estruturacao_pleito_reajuste",
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": ["ev-1"],
            },
            "service_candidates": [
                {
                    "service_id": "estruturacao_pleito_reajuste",
                    "supporting_signal_ids": ["mature_no_reajuste"],
                    "evidence_ids": ["ev-1"],
                }
            ],
            "evidence_ids": ["ev-1"],
            "micro_offer_code": "REAJUSTE_CHECK",
        }
    ]
    contacts = [
        {
            "cnpj14": "01449930000190",
            "commercial_contact_state": "CONTACT_READY",
            "contacts": [
                {
                    "email": "licitacoes@demo000obra.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "VERIFIED",
                    "enrollable": True,
                    "recommended": True,
                    "email_send_ready": True,  # stale false positive — must be recomputed false
                    "provenance": {
                        "source_type": "site",
                        "source_url": "https://demo000obra.com.br/contato",
                    },
                }
            ],
        }
    ]
    leads = build_leads(universe, intel, contacts)
    assert len(leads) == 1
    lead = leads[0]
    assert lead.get("email_send_ready") is False
    ct = (lead.get("contacts") or [None])[0]
    assert ct is not None
    assert ct.get("email_send_ready") is False
    assert ct.get("enrollable") is False
    assert ct.get("provenance_chain_valid") is False
    assert ct.get("root_source_type") in {
        RootSourceType.DEMO.value,
        RootSourceType.TEST_FIXTURE.value,
    }


def test_export_mapping_blocks_generic_even_with_real_provenance(tmp_path: Path) -> None:
    universe = [
        {
            "cnpj14": "12345678000199",
            "outreach_eligibility": "ELIGIBLE",
            "target_fit_class": "TARGET_CONFIRMED",
            "construction_evidence": {
                "sector_fit": "CONFIRMED_ENGINEERING",
                "target_fit_class": "TARGET_CONFIRMED",
                "relevant_contract_count": 4,
            },
            "portfolio": {"pass_contract_count": 4},
            "canonical_universe_member": True,
            "razao_social": "EMPRESA TARGET PAVIMENTACAO LTDA",
            "company_name": "EMPRESA TARGET PAVIMENTACAO LTDA",
            "official_domain": "empresa-target.com.br",
        }
    ]
    intel = [
        {
            "cnpj14": "12345678000199",
            "razao_social": "EMPRESA TARGET PAVIMENTACAO LTDA",
            "why_now": {
                "summary": (
                    "aditivo recente no contrato de EMPRESA TARGET de pavimentação asfáltica CBUQ com a Pref. Coxilha"
                ),
                "temporal_fact": (
                    "aditivo recente no contrato de EMPRESA TARGET de pavimentação asfáltica CBUQ com a Pref. Coxilha"
                ),
                "evidence_ids": ["ev-1"],
            },
            "offer": {
                "service_code": "estruturacao_pleito_reajuste",
                "entry_offer": "REAJUSTE_CHECK",
            },
            "messaging": {
                "why_this_account": (
                    "EMPRESA TARGET com execução pública de pavimentação — "
                    "objeto: pavimentação asfáltica CBUQ; órgão: Pref. Coxilha"
                ),
                "fact_to_mention": ("objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha; UF RS"),
                "cta": "Posso te mandar o recorte público?",
            },
            "primary_service": {
                "service_id": "estruturacao_pleito_reajuste",
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": ["ev-1"],
            },
            "service_candidates": [
                {
                    "service_id": "estruturacao_pleito_reajuste",
                    "supporting_signal_ids": ["mature_no_reajuste"],
                    "evidence_ids": ["ev-1"],
                }
            ],
            "evidence_ids": ["ev-1"],
            "micro_offer_code": "REAJUSTE_CHECK",
        }
    ]
    contacts = [
        {
            "cnpj14": "12345678000199",
            "contacts": [
                {
                    "email": "contato@empresa-target.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OBSERVED",
                    "enrollable": True,
                    "provenance": {
                        "source_type": "site",
                        "source_url": "https://empresa-target.com.br/contato",
                    },
                }
            ],
        }
    ]
    leads = build_leads(universe, intel, contacts)
    assert leads[0].get("email_send_ready") is False
    assert leads[0]["contacts"][0].get("provenance_chain_valid") is True


# ── human review mint ban ───────────────────────────────────────────────────


def test_machine_cannot_mint_human_review_approved() -> None:
    assert machine_review_status(structural_pass=True) == MACHINE_REVIEW_PASS
    assert machine_review_status(structural_pass=True) != HUMAN_REVIEW_APPROVED
    for forbidden in ("grok", "pytest", "ci", "automation", "script", "claude", "llm"):
        assert is_forbidden_reviewer(forbidden)
        with pytest.raises(ValueError, match="cannot be minted"):
            mint_human_review_decision(
                reviewer=forbidden,
                decision="APPROVED",
                evidence_inspected=["contact_page"],
            )


def test_real_human_can_mint_approval() -> None:
    d = mint_human_review_decision(
        reviewer="tiago.sasaki",
        decision="APPROVED",
        evidence_inspected=["official_site", "cnpj_match"],
    )
    assert d["status"] == HUMAN_REVIEW_APPROVED
    assert d["reviewer"] == "tiago.sasaki"
    assert d["reviewed_at"]
    assert d["evidence_inspected"]


# ── contact evaluate helper ─────────────────────────────────────────────────


def test_evaluate_contact_provenance_demo_siemens_shape() -> None:
    """Shape from contaminated pilot-200 artifacts (real CNPJ + demo email)."""
    contact = {
        "email": "licitacoes@demo000obra.com.br",
        "ownership_status": "COMPANY_OWNED",
        "verification_status": "VERIFIED",
        "enrollable": True,
        "official_domain": "demo000obra.com.br",
        "source": {
            "source_type": "site",
            "source_url": "https://demo000obra.com.br/contato",
            "notes": "Institutional site extract (no private social scrape)",
        },
    }
    res = evaluate_contact_provenance(contact)
    assert res.provenance_chain_valid is False
    assert res.root_source_type == RootSourceType.DEMO.value
    assert "sticky_verification_ignored:VERIFIED" in res.taint_reasons or any("demo" in t for t in res.taint_reasons)
