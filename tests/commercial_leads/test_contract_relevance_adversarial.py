"""Adversarial tests for hierarchical contract relevance — drives shipped code."""

from __future__ import annotations

import pytest

from scripts.commercial_leads.contract_relevance import (
    classify_contract_relevance,
    filter_relevant_contracts,
)


@pytest.mark.parametrize(
    "objeto",
    [
        "projeto de software para gestão escolar",
        "projeto cultural de teatro comunitário",
        "serviço de limpeza e conservação predial",
        "manutenção de veículo leve e pesado",
        "manutenção de impressora e multifuncionais",
        "consultoria contábil e fiscal",
        "terceirização de mão de obra com dedicação exclusiva",
        "fornecimento de autopeças e componentes automotivos",
        "aquisição de refeições para servidores",
        "locação de veículos com motorista",
    ],
)
def test_generic_or_oos_objects_fail_relevance(objeto: str) -> None:
    r = classify_contract_relevance(objeto)
    assert r.status in ("FAIL", "REVIEW"), (objeto, r)
    assert r.status != "PASS"


@pytest.mark.parametrize(
    "objeto",
    [
        "projeto estrutural de edificação escolar",
        "fiscalização de obra de pavimentação asfáltica",
        "pavimentação asfáltica de vias urbanas",
        "drenagem urbana e galerias",
        "construção de escola municipal em alvenaria",
        "reforma predial com recuperação estrutural",
        "saneamento básico e rede de esgoto",
        "terraplenagem e infraestrutura viária",
        "execução de obra de engenharia sob empreitada",
        "serviços técnicos especializados de engenharia e arquitetura",
    ],
)
def test_engineering_objects_pass_relevance(objeto: str) -> None:
    r = classify_contract_relevance(objeto)
    assert r.status == "PASS", (objeto, r.reason_codes, r.as_dict())


def test_weak_token_alone_never_passes() -> None:
    for weak in ("projeto", "serviço", "manutenção", "consultoria", "fornecimento"):
        r = classify_contract_relevance(weak)
        assert r.status == "FAIL"
        assert "weak_token_alone" in r.reason_codes or "no_relevance_evidence" in r.reason_codes


@pytest.mark.parametrize(
    "objeto",
    [
        "infraestrutura de TI",
        "infraestrutura de rede de dados",
        "serviços de infraestrutura de telecomunicações",
        "infraestrutura de tecnologia da informação",
        "contratação de infraestrutura cloud e datacenter",
    ],
)
def test_infraestrutura_ti_telecom_never_passes(objeto: str) -> None:
    """Bare/IT 'infraestrutura' must not qualify as engineering (skeptic finding)."""
    r = classify_contract_relevance(objeto)
    assert r.status != "PASS", (objeto, r.as_dict())


def test_infraestrutura_viaria_still_passes() -> None:
    r = classify_contract_relevance("obras de infraestrutura viária e pavimentação")
    assert r.status == "PASS"


def test_manutencao_de_ponte_passes_manutencao_veiculo_fails() -> None:
    assert classify_contract_relevance("manutenção de ponte e estrutura").status == "PASS"
    assert classify_contract_relevance("manutenção de veículos da frota").status == "FAIL"


def test_empty_object_fails() -> None:
    assert classify_contract_relevance(None).status == "FAIL"
    assert classify_contract_relevance("").status == "FAIL"


def test_filter_relevant_contracts_splits() -> None:
    rows = [
        {"objeto_contrato": "pavimentação asfáltica", "id": 1},
        {"objeto_contrato": "fornecimento de autopeças", "id": 2},
    ]
    kept, excl = filter_relevant_contracts(rows)
    assert len(kept) == 1 and kept[0]["id"] == 1
    assert len(excl) == 1 and excl[0]["id"] == 2
    assert "contract_relevance" in kept[0]
