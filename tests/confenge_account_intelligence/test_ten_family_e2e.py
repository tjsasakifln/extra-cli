"""Golden: all 10 service families survive evidence → dossier → bridge → canonical/Warmbly.

Does not re-implement the router; drives build_dossier + adapt + confenge.service.v1.
"""

from __future__ import annotations

import pytest

from scripts.confenge_account_intelligence.pipeline import build_dossier
from scripts.confenge_outreach_pipeline.adapt import intelligence_dossier_to_bridge_row
from scripts.confenge_service_contract.mapping import map_to_canonical, map_to_warmbly


def _base(**overrides):
    row = {
        "cnpj": "12345678000199",
        "cnpj14": "12345678000199",
        "razao_social": "CONSTRUTORA GOLDEN FAMILIA LTDA",
        "nome_fantasia": "Golden",
        "municipio": "Curitiba",
        "uf": "PR",
        "as_of": "2026-08-01",
        "commercial_state": "NEW",
        "activity_class": "CONSTRUCTION_CONTRACTOR",
        "signals": {},
        "contracts": [],
        "facts": [],
        "evidence": [],
    }
    row.update(overrides)
    return row


# Each case: bag overrides → expected extra_cli primary_service_id
CASES = {
    "reajuste": (
        {
            "contracts": [
                {
                    "id": "ct-r1",
                    "object": "Pavimentação asfáltica etapa única em via municipal",
                    "value_brl": 2_000_000,
                    "start_date": "2023-01-01",
                    "age_days": 900,
                    "orgao": "DEINFRA-PR",
                    "uf": "PR",
                    "has_reajuste": False,
                    "has_addendum": False,
                }
            ],
            "facts": [
                {
                    "id": "f1",
                    "text": "Contrato maduro sem termo de reajuste no material.",
                    "epistemic_class": "confirmed",
                    "confidence": 0.9,
                    "evidence_ids": ["ct-r1"],
                }
            ],
        },
        "estruturacao_pleito_reajuste",
        "REAJUSTE",
        "REAJUSTE",
    ),
    "reequilibrio": (
        {
            "contracts": [
                {
                    "id": "ct-eq",
                    "object": "Obra de saneamento — menção a reequilíbrio econômico",
                    "value_brl": 5_000_000,
                    "start_date": "2024-01-01",
                    "age_days": 400,
                    "reequilibrio_mention": True,
                    "orgao": "SANEPAR",
                    "uf": "PR",
                }
            ],
        },
        "reequilibrio_economico_financeiro",
        "REEQUILIBRIO",
        "REEQUILIBRIO",
    ),
    "aditivos": (
        {
            "contracts": [
                {
                    "id": "ct-ad",
                    "object": "Execução de obra civil com termo aditivo quantitativo",
                    "value_brl": 3_000_000,
                    "has_addendum": True,
                    "addendum_count": 2,
                    "orgao": "Prefeitura",
                    "uf": "SC",
                }
            ],
        },
        "aditivos_extracontratuais",
        "ADITIVOS",
        "ADITIVOS",
    ),
    "medicoes": (
        {
            "contracts": [
                {
                    "id": "ct-med",
                    "object": "Obra de drenagem com glosa e medição contestada",
                    "value_brl": 1_500_000,
                    "glosa_signals": True,
                    "measurement_issues": True,
                    "orgao": "DNIT",
                    "uf": "RS",
                }
            ],
        },
        "medicoes_glosas_memoria",
        "MEDICOES",
        "MEDICOES",
    ),
    "orcamento_bdi": (
        {
            "contracts": [
                {
                    "id": "ct-bdi",
                    "object": "Pacote com planilha orçamentária e BDI de obra de edificação",
                    "value_brl": 8_000_000,
                    "budget_or_bdi_signal": True,
                    "orgao": "CEF",
                    "uf": "SP",
                }
            ],
        },
        "auditoria_orcamento_bdi",
        "ORCAMENTO_BDI",
        "PLANILHAS",
    ),
    "gestao": (
        {
            "contracts": [
                {
                    "id": f"ct-g{i}",
                    "object": f"execução de obra de infraestrutura {i}",
                    "value_brl": 1_000_000 + i,
                    "start_date": "2023-01-01",
                    "age_days": 700,
                    "has_reajuste": False,
                    "orgao": f"Orgão {i}",
                    "uf": "MG",
                }
                for i in range(4)
            ],
            "signals": {},
        },
        "gestao_monitoramento_contratual",
        "MONITORAMENTO_CONTRATUAL",
        "MONITORAMENTO_CONTRATUAL",
    ),
    "licitacoes": (
        {
            "contracts": [
                {
                    "id": "ct-lic",
                    "object": "Participação em edital de licitação e proposta comercial de engenharia",
                    "value_brl": 500_000,
                    "tender_or_proposal_signal": True,
                    "orgao": "Município",
                    "uf": "BA",
                }
            ],
        },
        "apoio_licitacoes_propostas",
        "APOIO_LICITACAO",
        "APOIO_LICITACAO",
    ),
    "inteligencia": (
        {
            "contracts": [],
            "facts": [],
            "signals": {},
        },
        "diagnostico_contratual_b2g",  # insufficient → discovery primary
        "DIAGNOSTICO",
        "DIAGNOSTICO",
    ),
    "diagnostico": (
        {
            "contracts": [
                {
                    "id": "ct-d1",
                    "object": "Serviço pontual de engenharia consultiva sem aditivo nem glosa",
                    "value_brl": 80_000,
                    "orgao": "Órgão X",
                    "uf": "GO",
                    # no start_date → not mature; single contract → discovery
                }
            ],
            "signals": {},
        },
        "diagnostico_contratual_b2g",
        "DIAGNOSTICO",
        "DIAGNOSTICO",
    ),
    "backoffice": (
        {
            "contracts": [
                {
                    "id": f"ct-bo{i}",
                    "object": f"obra regional de reforma predial {i}",
                    "value_brl": 400_000 + i * 10_000,
                    "uf": "SC",
                    "orgao": "Pref.",
                }
                for i in range(3)
            ],
            "signals": {
                "regional_only": True,
                "concentrated_functions": True,
                "low_public_formalization": True,
            },
        },
        "reforco_temporario_backoffice",
        "BACKOFFICE",
        "BACKOFFICE",
    ),
}


@pytest.mark.parametrize("family", list(CASES.keys()))
def test_family_routes_and_maps(family: str) -> None:
    overrides, expected_sid, expected_can, expected_warm = CASES[family]
    d = build_dossier(_base(**overrides))
    sid = d["primary_service"]["service_id"]
    assert sid == expected_sid, f"{family}: primary={sid}"
    assert d.get("micro_offer_code"), f"{family}: micro_offer_code empty"
    assert d.get("why_this_account"), f"{family}: why_this_account empty"
    why_l = d["why_this_account"].lower()
    assert "empresa com portfólio público observável" not in why_l
    assert "empresa com momento comercial público" not in why_l
    bridge = intelligence_dossier_to_bridge_row(d)
    offer = bridge.get("offer") or {}
    assert offer.get("service_code")
    assert map_to_canonical(sid) == expected_can
    assert map_to_warmbly(sid) == expected_warm
    # approach_mode is NOT a valid micro_offer
    assert d["micro_offer_code"] not in {
        "revisao_independente_segunda_opiniao",
        "diagnostico_focal",
        "apoio_operacional",
        "diagnostico_inicial_exploratorio",
        "outsourcing_operacional_temporario",
    }


def test_ten_families_canonical_roundtrip() -> None:
    """All catalog families map bidirectionally without collapsing to REAJUSTE."""
    families = [
        "estruturacao_pleito_reajuste",
        "reequilibrio_economico_financeiro",
        "aditivos_extracontratuais",
        "medicoes_glosas_memoria",
        "auditoria_orcamento_bdi",
        "gestao_monitoramento_contratual",
        "apoio_licitacoes_propostas",
        "inteligencia_pncp_mercado",
        "diagnostico_contratual_b2g",
        "reforco_temporario_backoffice",
    ]
    warmbly_codes = set()
    for sid in families:
        can = map_to_canonical(sid)
        warm = map_to_warmbly(sid)
        warmbly_codes.add(warm)
        if sid != "estruturacao_pleito_reajuste":
            assert can != "REAJUSTE"
            assert warm != "REAJUSTE"
    assert len(warmbly_codes) >= 9
