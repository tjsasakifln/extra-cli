"""REAL_OFFICIAL_SITE must classify as trusted root (not unclassified taint)."""

from __future__ import annotations

from scripts.confenge_contact_resolution.provenance_trust import (
    TRUSTED_ROOTS,
    classify_root_source_type,
    evaluate_provenance_trust,
)
from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready


def test_real_official_site_enum_is_trusted() -> None:
    root, reasons = classify_root_source_type(
        source_type="REAL_OFFICIAL_SITE",
        source_url="https://encopav.com.br/contato",
        email="encopav@encopav.com.br",
    )
    assert root in TRUSTED_ROOTS
    assert not any("unclassified" in r for r in reasons)


def test_contact_page_maps_to_real_official_site() -> None:
    root, _ = classify_root_source_type(
        source_type="contact_page",
        source_url="https://encopav.com.br/contato",
        email="encopav@encopav.com.br",
    )
    assert root == "REAL_OFFICIAL_SITE"


def test_evaluate_provenance_trust_real_official_site_chain() -> None:
    prov = evaluate_provenance_trust(
        email="encopav@encopav.com.br",
        source_type="REAL_OFFICIAL_SITE",
        source_url="https://encopav.com.br/contato",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        provenance_chain=[
            {
                "source_type": "contact_page",
                "source_url": "https://encopav.com.br/contato",
                "method": "host_enrich_confirmed",
                "observed_at": "2026-08-10T06:03:00Z",
                "root": True,
            }
        ],
    )
    assert prov.provenance_chain_valid is True or prov.root_source_type in TRUSTED_ROOTS
    assert "unclassified_source_type:real_official_site" not in (
        prov.taint_reasons or []
    )


def test_send_ready_accepts_real_official_site_with_copy() -> None:
    company = {
        "cnpj14": "00061493000170",
        "razao_social": "ENCOPAV ENGENHARIA LTDA",
        "target_fit_class": "TARGET_CONFIRMED",
        "primary_service": {
            "service_id": "gestao_monitoramento_contratual",
            "supporting_signal_ids": ["multi_contract"],
            "evidence_ids": ["ev-1"],
            "factual_basis": "multi_contract_portfolio",
            "confidence": 0.6,
        },
        "why_you": "Carteira pública multi-contrato em SC.",
        "why_now": "Janela de revisão contratual 2026.",
        "observed_fact": "3 contratos públicos de pavimentação em 2025-2026.",
        "micro_offer": "gestao_monitoramento_contratual",
        "cta": "Conversar 15 min sobre gestão da carteira.",
        "copy_context": {
            "present": True,
            "hollow": False,
            "why_you": "Carteira pública multi-contrato em SC.",
            "why_now": "Janela de revisão contratual 2026.",
            "observed_fact": "3 contratos públicos de pavimentação em 2025-2026.",
            "micro_offer_code": "gestao_monitoramento_contratual",
            "cta": "Conversar 15 min sobre gestão da carteira.",
        },
    }
    res = evaluate_email_send_ready(
        company=company,
        email="encopav@encopav.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        factual_evidence=True,
        evidence_ids=["ev-1"],
        require_copy_context=True,
        source_type="REAL_OFFICIAL_SITE",
        source_url="https://encopav.com.br/contato",
        provenance_chain=[
            {
                "source_type": "contact_page",
                "source_url": "https://encopav.com.br/contato",
                "observed_at": "2026-08-10T06:03:00Z",
                "root": True,
            }
        ],
    )
    # Must not fail solely on unclassified REAL_OFFICIAL_SITE
    assert "taint:unclassified_source_type:real_official_site" not in res.reasons
    assert res.root_source_type != "UNKNOWN" or res.provenance_chain_valid
