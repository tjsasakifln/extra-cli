"""PROBABLE requires positive ICP evidence; absence is INSUFFICIENT_EVIDENCE."""

from __future__ import annotations

from scripts.confenge_universe.target_fit import (
    TARGET_CONFIRMED,
    TARGET_INSUFFICIENT_EVIDENCE,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
    classify_target_fit,
)


def test_unknown_supplier_is_insufficient_not_probable() -> None:
    d = classify_target_fit(razao_social="ACME SERVICOS DIVERSOS LTDA", contracts=[])
    assert d.target_fit_class == TARGET_INSUFFICIENT_EVIDENCE
    assert "insufficient_positive_icp_evidence" in d.target_fit_reason_codes or any(
        "insufficient" in r for r in d.target_fit_reason_codes
    )


def test_default_research_no_longer_emitted_as_probable() -> None:
    d = classify_target_fit(razao_social="EMPRESA GENERICA 123", contracts=[])
    assert d.target_fit_class != TARGET_PROBABLE_RESEARCH
    assert "default_research" not in d.target_fit_reason_codes


def test_cnae_engineering_alone_is_probable_with_evidence() -> None:
    d = classify_target_fit(
        razao_social="ENG CIVIL BETA LTDA",
        cnae_principal="4120400",
        contracts=[],
    )
    assert d.target_fit_class == TARGET_PROBABLE_RESEARCH
    assert any(e.get("type") == "CNAE_ENGINEERING" for e in d.target_fit_evidence)


def test_single_execution_contract_is_probable() -> None:
    d = classify_target_fit(
        razao_social="OBRAS DELTA LTDA",
        contracts=[
            {
                "id": "1",
                "objeto": "execução de obras de pavimentação asfáltica em via municipal",
                "valor_total": 500_000,
            }
        ],
    )
    assert d.target_fit_class == TARGET_PROBABLE_RESEARCH
    assert d.relevant_execution_contract_count == 1
    assert d.target_fit_evidence  # positive evidence required


def test_supply_only_is_out_not_probable() -> None:
    d = classify_target_fit(
        razao_social="FORNECEDORA DE MATERIAIS LTDA",
        contracts=[
            {
                "objeto": "fornecimento de materiais de construção para escola",
                "valor_total": 10_000,
            }
        ],
    )
    assert d.target_fit_class == TARGET_OUT_OF_SCOPE


def test_multi_execution_still_confirmed() -> None:
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
                "valor_total": 2_000_000,
            },
        ],
    )
    assert d.target_fit_class == TARGET_CONFIRMED
