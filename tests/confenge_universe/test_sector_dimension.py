"""Adversarial invariants for sector membership versus target-fit."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from scripts.commercial_leads.sector_fit import ContractHistoryAccumulator
from scripts.confenge_sector import (
    CONSTRUCTION_CONFIRMED,
    CONSTRUCTION_PROBABLE,
    NON_CONSTRUCTION,
    SECTOR_INSUFFICIENT_EVIDENCE,
    classify_company_sector,
)
from scripts.confenge_universe import construction as construction_module
from scripts.confenge_universe.target_fit import TARGET_OUT_OF_SCOPE


def test_sector_classification_is_explicit_and_independent() -> None:
    confirmed = classify_company_sector(
        razao_social="ENGENHARIA EXEMPLO LTDA",
        cnae_principal="7112-0/00",
        contracts=[],
    )
    probable = classify_company_sector(
        razao_social="CONSTRUTORA EM PESQUISA LTDA",
        contracts=[],
    )
    non_construction = classify_company_sector(
        razao_social="FARMACIA EXEMPLO LTDA",
        cnae_principal="4771-7/01",
        contracts=[],
    )
    unresolved = classify_company_sector(razao_social="ALFA LTDA", contracts=[])

    assert confirmed.sector_class == CONSTRUCTION_CONFIRMED
    assert probable.sector_class == CONSTRUCTION_PROBABLE
    assert non_construction.sector_class == NON_CONSTRUCTION
    assert unresolved.sector_class == SECTOR_INSUFFICIENT_EVIDENCE


def test_streaming_sector_history_keeps_the_full_denominator() -> None:
    history = ContractHistoryAccumulator()
    for i in range(5_000):
        history.add(
            {
                "contrato_id": f"contract-{i}",
                "objeto_contrato": "Execucao de obra de pavimentacao asfaltica",
                "orgao_cnpj": f"{i % 100:014d}",
                "data_publicacao": "2026-01-01",
            }
        )

    stats = history.as_stats()
    assert stats["total_contract_count_full_history"] == 5_000
    assert stats["relevant_contract_count"] == 5_000
    assert stats["denominator_invariant_ok"] is True


def test_target_out_of_scope_cannot_remove_confirmed_construction(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        construction_module,
        "classify_target_fit",
        lambda **_: SimpleNamespace(
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.9,
            target_fit_evidence=[],
            target_fit_reason_codes=["commercially_out_for_now"],
            target_fit_version="test-target-fit",
            relevant_execution_contract_count=0,
        ),
    )

    evidence = construction_module.assess_construction(
        razao_social="ENGENHARIA EXEMPLO LTDA",
        cnae_principal="7112-0/00",
        contracts=[],
    )

    assert evidence.sector_class == CONSTRUCTION_CONFIRMED
    assert evidence.is_construction is True
    assert evidence.target_fit_class == TARGET_OUT_OF_SCOPE


def test_warmbly_mapping_never_uses_target_out_as_sector_membership_proxy() -> None:
    from scripts.warmbly_bridge import mapping

    source = inspect.getsource(mapping.map_lead)
    assert 'pub_class != "TARGET_OUT_OF_SCOPE"' not in source
    assert "construction_universe_member" in source


def test_non_construction_is_sector_evidence_not_target_fit_inference() -> None:
    evidence = construction_module.assess_construction(
        razao_social="FARMACIA EXEMPLO LTDA",
        cnae_principal="4771-7/01",
        contracts=[
            {
                "contrato_id": "medicine-1",
                "objeto_contrato": "aquisição de medicamentos hospitalares",
            }
        ],
    )

    assert evidence.sector_class == NON_CONSTRUCTION
    assert evidence.is_construction is False
    assert evidence.epistemic_class == "EVIDENCE"
