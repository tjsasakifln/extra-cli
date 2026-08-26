from __future__ import annotations

from scripts.decision_unit_intelligence.batch_contact_metadata import attach_route_evidence
from scripts.decision_unit_intelligence.evidence import verified_page_document_bytes
from scripts.warmbly_bridge.mapping import _map_contact
from tests.recipient_attestation_fixtures import exact_page_attestation


def test_exact_registry_association_proof_survives_contact_projection() -> None:
    cnpj = "12345678000190"
    proof = {
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        "mailbox_person_evidence": "UNKNOWN",
        "official_match_status": "MATCHED",
        "official_authority": "RECEITA_FEDERAL",
        "official_release_id": "rfb-2026-08",
        "registry_cnpj14": cnpj,
        "source_provenance": {
            "release_id": "rfb-2026-08",
            "source_label": "rfb_public_cadastral_via_opencnpj",
        },
    }
    account = {
        "routes": [
            {
                "route_id": "registry-route-1",
                "channel_value": "empresa@gmail.com",
                "source_type": "company_registry",
                "observed_at": "2026-08-24T12:00:00Z",
                "evidence_ids": ["registry-evidence-1"],
                "ownership": "COMPANY_OWNED",
                "freshness": "FRESH",
                "suppression": "NONE",
                "epistemic_class": "OBSERVED",
                "extra": proof,
            }
        ]
    }

    contact = attach_route_evidence(
        [{"source_contact_id": "registry-route-1", "email": "empresa@gmail.com"}],
        account=account,
    )[0]

    for key, value in proof.items():
        assert contact[key] == value
    assert contact["source_reference"] == "registry-evidence-1"
    assert contact["route_freshness"] == "FRESH"
    assert contact["route_suppression"] == "NONE"
    assert contact["provenance"]["epistemic_class"] == "OBSERVED"


def test_page_document_witness_survives_projection_and_warmbly_mapping() -> None:
    cnpj = "12345678000190"
    mailbox = "contato@empresa.example"
    source_url = "https://empresa.example/contato"
    observed_at = "2026-08-24T12:00:00Z"
    attestation = exact_page_attestation(
        account=cnpj,
        mailbox=mailbox,
        source_url=source_url,
        observed_at=observed_at,
    )
    account = {
        "routes": [
            {
                "route_id": "page-route-1",
                "channel_value": mailbox,
                "source_type": "company_website",
                "source_url": source_url,
                "observed_at": observed_at,
                "ownership": "COMPANY_OWNED",
                "freshness": "FRESH",
                "suppression": "NONE",
                "epistemic_class": "OBSERVED",
                "extra": {"official_domain": "empresa.example", **attestation},
            }
        ]
    }

    projected = attach_route_evidence(
        [{"source_contact_id": "page-route-1", "email": mailbox}],
        account=account,
    )[0]
    mapped = _map_contact(projected, idx=0, cnpj=cnpj)

    assert mapped["page_document_witness"] == attestation["page_document_witness"]
    assert verified_page_document_bytes(
        mapped["page_document_witness"],
        expected_sha256=mapped["page_cnpj_evidence_sha256"],
    ) is not None
