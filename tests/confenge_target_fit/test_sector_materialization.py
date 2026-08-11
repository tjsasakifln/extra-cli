"""Sector persistence remains independent and reconsiderable with target-fit."""

from __future__ import annotations

from scripts.confenge_sector import CONSTRUCTION_CONFIRMED
from scripts.confenge_sector.store import materialize_sector
from scripts.confenge_target_fit.loader import company_input_from_dict


def test_construction_with_insufficient_target_fit_has_own_materialization() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "12345678",
            "razao_social": "ENGENHARIA EXEMPLO LTDA",
            "cnae_principal": "7112-0/00",
            "contracts": [],
            "source_watermark": "wm-1",
        }
    )

    sector = materialize_sector(company)

    assert sector.sector_class == CONSTRUCTION_CONFIRMED
    assert sector.company_key == "cnpj_root:12345678"
    assert sector.source_watermark == "wm-1"


def test_sector_fingerprint_changes_when_new_evidence_arrives() -> None:
    before = company_input_from_dict(
        {
            "cnpj_raiz": "12345678",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "contracts": [],
        }
    )
    after = company_input_from_dict(
        {
            "cnpj_raiz": "12345678",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "contracts": [
                {
                    "contrato_id": "new-evidence",
                    "objeto_contrato": "execução de obra de pavimentação",
                    "orgao_cnpj": "12340000000100",
                }
            ],
        }
    )

    assert materialize_sector(before).input_fingerprint != materialize_sector(after).input_fingerprint


def test_sector_materialization_uses_only_observed_valid_establishment() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "branch_cnpjs": ["11222333000181", "11222333000100"],
        }
    )

    sector = materialize_sector(company)

    assert sector.representative_cnpj14 == "11222333000181"


def test_sector_materialization_does_not_invent_establishment() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "branch_cnpjs": ["11222333000100"],
        }
    )

    assert materialize_sector(company).representative_cnpj14 is None


def test_sector_evidence_does_not_embed_target_fit_as_sector_proof() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "construction_evidence": {
                "sector_class": "CONSTRUCTION_CONFIRMED",
                "confidence": 0.9,
                "provenance": [
                    {"source": "commercial_leads.sector_fit", "classification": "CONFIRMED"},
                    {"source": "confenge_universe.target_fit", "target_fit_class": "TARGET_CONFIRMED"},
                ],
            },
        }
    )

    sector = materialize_sector(company)

    assert sector.sector_evidence == [
        {"source": "commercial_leads.sector_fit", "classification": "CONFIRMED"}
    ]
