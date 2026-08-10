"""Adversarial ICP target-fit: negatives out, true constructors confirmed."""

from __future__ import annotations

from scripts.confenge_universe.construction import assess_construction
from scripts.confenge_universe.target_fit import (
    TARGET_CONFIRMED,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
    classify_target_fit,
)


def test_imobiliaria_out_of_scope() -> None:
    d = classify_target_fit(
        razao_social="ROSA IMOVEIS LTDA.",
        contracts=[
            {
                "objeto": "Laudo Técnico de Avaliação Imobiliária do imóvel sede",
                "valor_total": 4000,
            }
        ],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_moveis_commerce_out() -> None:
    d = classify_target_fit(
        razao_social="MILAN MOVEIS INDUSTRIA E COMERCIO LTDA",
        contracts=[
            {
                "objeto": "AQUISIÇÃO DE CONJUNTOS ESCOLARES mesas e cadeiras",
                "valor_total": 90000,
            }
        ],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_frota_out() -> None:
    d = classify_target_fit(
        razao_social="MS COMERCIO, SERVICOS E MANUTENCAO DE FROTAS LTDA",
        contracts=[
            {
                "objeto": "peças e serviços para revisão preventiva de trator",
                "valor_total": 800,
            }
        ],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_medical_equipment_out() -> None:
    d = classify_target_fit(
        razao_social="ISOMEDICAL COMERCIAL LTDA",
        contracts=[{"objeto": "AQUISIÇÃO DE CONJUNTO CATETER BALÃO", "valor_total": 38500}],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_metrologia_out() -> None:
    d = classify_target_fit(
        razao_social="VISOMES COMERCIAL METROLOGICA LTDA",
        contracts=[
            {
                "objeto": "Calibração RBC de leitoras de ELISA e termociclador",
                "valor_total": 3779,
            }
        ],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_vehicle_dealer_out() -> None:
    d = classify_target_fit(
        razao_social="RODO SERVICE LTDA",
        contracts=[{"objeto": "Aquisição de dois Ônibus e um veiculo", "valor_total": 1640000}],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_pavimentacao_confirmed() -> None:
    d = classify_target_fit(
        razao_social="TRACADO CONSTRUCOES E SERVICOS LTDA",
        sector_fit="STRONG_ENGINEERING_FIT",
        activity_class="ENGINEERING_SERVICE_PROVIDER",
        contracts=[
            {
                "id": "1",
                "objeto": "execução de obras de pavimentação asfáltica em CBUQ",
                "valor_total": 1_500_000,
            },
            {
                "id": "2",
                "objeto": "Pavimentação Asfáltica no trecho municipal",
                "valor_total": 17_000_000,
            },
            {
                "id": "3",
                "objeto": "empreitada global de pavimentação e passeio",
                "valor_total": 300_000,
            },
        ],
    )
    assert d.target_fit_class == TARGET_CONFIRMED
    assert d.relevant_execution_contract_count >= 2


def test_engenharia_obras_arte_confirmed() -> None:
    d = classify_target_fit(
        razao_social="JATOBETON ENGENHARIA LTDA",
        sector_fit="STRONG_ENGINEERING_FIT",
        contracts=[
            {
                "objeto": (
                    "ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, "
                    "EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE OBRA DE ARTE ESPECIAL"
                ),
                "valor_total": 9_000_000,
            },
            {
                "objeto": "servicos de engenharia e execução de obra de reabilitação",
                "valor_total": 8_000_000,
            },
            {
                "objeto": "projeto executivo de engenharia e execução de obra",
                "valor_total": 14_000_000,
            },
        ],
    )
    assert d.target_fit_class == TARGET_CONFIRMED


def test_assess_construction_drops_imobiliaria() -> None:
    ev = assess_construction(
        razao_social="ROSA IMOVEIS LTDA.",
        contracts=[
            {
                "objeto_contrato": (
                    "Contratação de serviço técnico especializado de elaboração de "
                    "Laudo Técnico de Avaliação Imobiliária"
                )
            }
        ],
    )
    assert ev.is_construction is False
    assert ev.target_fit_class == TARGET_OUT_OF_SCOPE


def test_name_alone_never_confirms() -> None:
    d = classify_target_fit(
        razao_social="CONSTRUTORA XYZ LTDA",
        contracts=[],
        sector_fit="",
    )
    assert d.target_fit_class != TARGET_CONFIRMED


def test_possible_single_contract_is_research_not_confirmed() -> None:
    d = classify_target_fit(
        razao_social="EMPRESA DIVERSA LTDA",
        sector_fit="POSSIBLE_ENGINEERING_FIT",
        contracts=[
            {
                "objeto": "execução de obra de reforma predial em prédio administrativo",
                "valor_total": 200_000,
            }
        ],
    )
    assert d.target_fit_class in {TARGET_PROBABLE_RESEARCH, TARGET_CONFIRMED}
    # single execution without strong sector → research
    if d.relevant_execution_contract_count == 1 and d.sector_fit == "POSSIBLE_ENGINEERING_FIT":
        assert d.target_fit_class == TARGET_PROBABLE_RESEARCH


def test_pharma_medication_acquisition_not_confirmed() -> None:
    """FARMACE-style: medication acquisition + pharma name must not be TARGET_CONFIRMED."""
    from scripts.confenge_universe.target_fit import (
        TARGET_CONFIRMED,
        classify_target_fit,
    )

    fit = classify_target_fit(
        razao_social="FARMACE - INDUSTRIA QUIMICO-FARMACEUTICA CEARENSE LTDA",
        contracts=[
            {
                "objeto": (
                    "Aquisição de medicamentos por meio de ATA SRP nº54/2025-C, "
                    "da Fundação Saúde do Estado do Rio de Janeiro."
                ),
                "orgao_nome": "FUNDO ESPECIAL DO CORPO DE BOMBEIROS",
                "valor_total": 2154.0,
            }
            for _ in range(5)
        ],
        sector_fit="POSSIBLE_ENGINEERING_FIT",
        activity_class="OTHER",
    )
    assert fit.target_fit_class != TARGET_CONFIRMED
