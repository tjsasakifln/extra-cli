from __future__ import annotations

from scripts.decision_unit_intelligence.batch_contact_metadata import attach_route_evidence


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
