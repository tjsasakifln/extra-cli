"""Supplier sector-fit classification — gold standard full-history policy."""

from __future__ import annotations

from datetime import date, timedelta

from scripts.commercial_leads.sector_fit import (
    CLASS_CONFIRMED,
    CLASS_OUT,
    CLASS_POSSIBLE,
    CLASS_STRONG,
    CLASS_UNKNOWN,
    CLASS_CONFLICTING,
    PUBLISHABLE,
    assert_denominator_invariant,
    classify_supplier_sector_fit,
)
from scripts.commercial_leads.commercial_validity import evaluate_supplier_validity
from scripts.commercial_leads.geography import classify_geography


def _ctr(
    obj: str,
    *,
    orgao: str = "org-1",
    pub: date | None = None,
    uf: str = "SC",
) -> dict:
    return {
        "objeto_contrato": obj,
        "uf": uf,
        "orgao_cnpj": orgao,
        "orgao_nome": orgao,
        "data_publicacao": (pub or date(2025, 1, 15)).isoformat(),
    }


def _strong_history() -> list[dict]:
    """Meets gold STRONG thresholds without CNAE: >=3 relevant, ratio>=0.7, 2+ agencies, 180d span, 2+ objects."""
    d0 = date(2024, 1, 1)
    return [
        _ctr("execução de obras e serviços de engenharia para estradas", orgao="org-a", pub=d0),
        _ctr("pavimentação asfáltica de vias urbanas", orgao="org-b", pub=d0 + timedelta(days=200)),
        _ctr("terraplenagem e drenagem urbana", orgao="org-a", pub=d0 + timedelta(days=400)),
        _ctr("construção de escola municipal em alvenaria", orgao="org-b", pub=d0 + timedelta(days=500)),
    ]


def test_autopecas_out_of_scope() -> None:
    d = classify_supplier_sector_fit(
        razao_social="MG AUTO PECAS E SERVICOS LTDA",
        contracts=[_ctr("manutenção de veículos e fornecimento de peças")],
    )
    assert d.classification == CLASS_OUT
    assert d.classification not in PUBLISHABLE
    assert d.reason_codes
    assert_denominator_invariant(d)


def test_construtora_strong_with_full_history() -> None:
    d = classify_supplier_sector_fit(
        razao_social="CONSTRUBRAS CONSTRUTORA LTDA",
        contracts=_strong_history(),
    )
    assert d.classification in (CLASS_STRONG, CLASS_CONFIRMED)
    assert d.publishable
    assert d.relevant_contract_count >= 3
    assert d.relevant_contract_ratio_full_history >= 0.70
    assert_denominator_invariant(d)


def test_cnae_engineering_confirmed() -> None:
    d = classify_supplier_sector_fit(
        razao_social="XYZ SERVICOS LTDA",
        cnae_principal="7112-0/00",
        contracts=[_ctr("projeto estrutural de edificação")],
    )
    assert d.classification == CLASS_CONFIRMED
    assert_denominator_invariant(d)


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
    assert d.classification not in PUBLISHABLE


def test_name_engineering_cnae_out_conflicting_or_out() -> None:
    d = classify_supplier_sector_fit(
        razao_social="ALFA ENGENHARIA LTDA",
        cnae_principal="4781-4/00",  # varejo
        contracts=[_ctr("fornecimento de materiais de escritório")],
    )
    assert d.classification in (CLASS_OUT, CLASS_CONFLICTING, CLASS_POSSIBLE, CLASS_UNKNOWN)
    assert d.classification not in PUBLISHABLE


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
        "relevant_contract_ratio_full_history",
        "total_contract_count_full_history",
        "activity_class",
        "denominator_invariant_ok",
    ):
        assert key in payload


def test_publishable_requires_three_way_pass() -> None:
    contracts = _strong_history()
    for c in contracts:
        c["uf"] = "SC"
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


def test_single_relevant_contract_never_strong() -> None:
    """Gold rule: 1 relevant + 0 CNAE → max POSSIBLE."""
    d = classify_supplier_sector_fit(
        razao_social="QUALQUER EMPRESA LTDA",
        contracts=[_ctr("execução de obra de pavimentação asfáltica")],
    )
    assert d.relevant_contract_count == 1
    assert d.classification == CLASS_POSSIBLE
    assert d.classification not in PUBLISHABLE
    assert "single_relevant_contract_cap_possible" in d.reason_codes or d.classification == CLASS_POSSIBLE


def test_name_alone_never_publishable() -> None:
    d = classify_supplier_sector_fit(
        razao_social="OMEGA ENGENHARIA E EMPREENDIMENTOS LTDA",
        contracts=[],
    )
    assert d.classification not in PUBLISHABLE


def test_denominator_contamination_impossible() -> None:
    """1 pavement + 9 food → ratio 0.10, never STRONG."""
    contracts = [_ctr("pavimentação asfáltica de vias urbanas", orgao="org-a")]
    for i in range(9):
        contracts.append(
            _ctr(
                "aquisição de refeições e alimentação para servidores",
                orgao=f"org-food-{i}",
                pub=date(2025, 3, 1),
            )
        )
    d = classify_supplier_sector_fit(
        razao_social="MISTA SERVICOS LTDA",
        contracts=contracts,
    )
    assert d.total_contract_count_full_history == 10
    assert d.relevant_contract_count == 1
    assert abs(d.relevant_contract_ratio_full_history - 0.10) < 1e-6
    assert d.classification != CLASS_STRONG
    assert d.classification != CLASS_CONFIRMED
    assert d.classification in (CLASS_POSSIBLE, CLASS_OUT, CLASS_CONFLICTING, CLASS_UNKNOWN)
    assert_denominator_invariant(d)


def test_two_obra_eight_limpeza_never_strong_without_cnae() -> None:
    contracts = [
        _ctr("execução de obra de engenharia civil", orgao="a", pub=date(2024, 1, 1)),
        _ctr("construção de escola municipal em alvenaria", orgao="b", pub=date(2024, 8, 1)),
    ]
    for i in range(8):
        contracts.append(
            _ctr(
                "serviço de limpeza e conservação predial",
                orgao=f"lim-{i}",
                pub=date(2025, 1, 1),
            )
        )
    d = classify_supplier_sector_fit(
        razao_social="BETA SERVICOS GERAIS LTDA",
        contracts=contracts,
    )
    assert d.relevant_contract_count == 2
    assert d.total_contract_count_full_history == 10
    assert abs(d.relevant_contract_ratio_full_history - 0.2) < 1e-6
    assert d.classification != CLASS_STRONG
    assert d.classification not in PUBLISHABLE
    assert_denominator_invariant(d)


def test_materials_supplier_not_engineering() -> None:
    d = classify_supplier_sector_fit(
        razao_social="SAO MIGUEL MATERIAIS P CONSTRUCAO LTDA",
        contracts=[
            _ctr("fornecimento de materiais de construção para reforma"),
            _ctr("aquisição de materiais de construção diversos"),
        ],
    )
    assert d.classification not in PUBLISHABLE
    assert d.activity_class in (
        "ENGINEERING_MATERIAL_SUPPLIER",
        "GENERAL_COMMERCE",
        "OTHER",
        "OUT_OF_SCOPE",
    ) or d.classification == CLASS_OUT
