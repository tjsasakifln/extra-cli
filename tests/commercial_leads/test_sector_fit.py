"""Supplier sector-fit classification — multi-evidence, not name-only."""

from __future__ import annotations

from scripts.commercial_leads.sector_fit import (
    CLASS_CONFIRMED,
    CLASS_OUT,
    CLASS_POSSIBLE,
    CLASS_STRONG,
    CLASS_UNKNOWN,
    PUBLISHABLE,
    classify_supplier_sector_fit,
)
from scripts.commercial_leads.commercial_validity import evaluate_supplier_validity
from scripts.commercial_leads.geography import classify_geography


def _ctr(obj: str) -> dict:
    return {"objeto_contrato": obj, "uf": "SC"}


def test_autopecas_out_of_scope() -> None:
    d = classify_supplier_sector_fit(
        razao_social="MG AUTO PECAS E SERVICOS LTDA",
        contracts=[_ctr("manutenção de veículos e fornecimento de peças")],
    )
    assert d.classification == CLASS_OUT
    assert d.classification not in PUBLISHABLE
    assert d.reason_codes


def test_construtora_strong_or_confirmed() -> None:
    d = classify_supplier_sector_fit(
        razao_social="CONSTRUBRAS CONSTRUTORA LTDA",
        contracts=[
            _ctr("execução de obras e serviços de engenharia para estradas"),
            _ctr("pavimentação asfáltica de vias urbanas"),
            _ctr("terraplenagem e drenagem"),
        ],
    )
    assert d.classification in (CLASS_STRONG, CLASS_CONFIRMED)
    assert d.publishable


def test_cnae_engineering_confirmed() -> None:
    d = classify_supplier_sector_fit(
        razao_social="XYZ SERVICOS LTDA",
        cnae_principal="7112-0/00",
        contracts=[_ctr("projeto estrutural de edificação")],
    )
    assert d.classification == CLASS_CONFIRMED


def test_churrascaria_out() -> None:
    d = classify_supplier_sector_fit(
        razao_social="CHURRASCARIA E PIZZARIA CHOPINHO LTDA",
        contracts=[_ctr("aquisição de refeições para servidores")],
    )
    assert d.classification == CLASS_OUT


def test_terceirizacao_out() -> None:
    d = classify_supplier_sector_fit(
        razao_social="PRO ACTIVE TERCEIRIZACAO LTDA",
        contracts=[
            _ctr("terceirização de mão de obra com dedicação exclusiva de mão de obra"),
        ],
    )
    assert d.classification in (CLASS_OUT, CLASS_POSSIBLE, CLASS_UNKNOWN)
    assert d.classification not in PUBLISHABLE or d.relevant_contract_ratio < 0.6


def test_name_engineering_cnae_out_conflicting_or_out() -> None:
    d = classify_supplier_sector_fit(
        razao_social="ALFA ENGENHARIA LTDA",
        cnae_principal="4781-4/00",  # varejo
        contracts=[_ctr("fornecimento de materiais de escritório")],
    )
    assert d.classification in (CLASS_OUT, "CONFLICTING", CLASS_POSSIBLE, CLASS_UNKNOWN)
    assert d.classification not in PUBLISHABLE or d.confidence < 0.9


def test_missing_data_unknown() -> None:
    d = classify_supplier_sector_fit(razao_social="EMPRESA GENERICA LTDA", contracts=[])
    assert d.classification in (CLASS_UNKNOWN, CLASS_POSSIBLE)


def test_provenance_fields_present() -> None:
    d = classify_supplier_sector_fit(
        razao_social="BETA ENGENHARIA E CONSTRUCOES LTDA",
        contracts=[_ctr("obra de engenharia civil")],
        run_id="test-run",
    )
    payload = d.as_dict()
    for key in (
        "classification",
        "confidence",
        "rule_version",
        "evidence",
        "reason_codes",
        "conflicting_evidence",
        "data_sources",
        "run_id",
    ):
        assert key in payload


def test_publishable_requires_three_way_pass() -> None:
    contracts = [
        _ctr("execução de obra de engenharia"),
        _ctr("pavimentação asfáltica"),
    ]
    v, sector, geo = evaluate_supplier_validity(
        razao_social="GAMA CONSTRUTORA LTDA",
        contracts=contracts,
        signals_fired=[{"signal_id": "near_expiry"}],
        score_total=5.0,
        allowed_ufs=["SC", "PR", "RS", "SP", "RJ", "MG"],
    )
    assert sector.classification in PUBLISHABLE
    assert v.contract_relevance == "PASS"
    assert v.commercial_signal_fit == "PASS"
    assert v.geography_fit == "PASS"
    assert v.publishable is True


def test_possible_not_publishable() -> None:
    v, sector, _geo = evaluate_supplier_validity(
        razao_social="DELTA SERVICOS LTDA",
        contracts=[_ctr("apoio técnico administrativo genérico com projeto interno")],
        signals_fired=[{"signal_id": "x"}],
        score_total=5.0,
        allowed_ufs=["SC"],
    )
    assert sector.classification not in PUBLISHABLE or v.publishable is False


def test_uf_null_not_auto_pass() -> None:
    r = classify_geography(uf=None, allowed_ufs=["SC", "PR"])
    assert r.status in ("GEOGRAPHY_UNKNOWN", "REVIEW_REQUIRED")
    assert r.reason == "missing_geographic_evidence"


def test_uf_in_filter_passes() -> None:
    r = classify_geography(uf="SC", allowed_ufs=["SC", "PR"])
    assert r.status == "PASS"
