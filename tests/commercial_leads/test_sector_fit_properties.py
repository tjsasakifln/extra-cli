"""Property-based / adversarial properties for sector fit and denominator integrity."""

from __future__ import annotations

from datetime import date, timedelta

from scripts.commercial_leads.sector_fit import (
    CLASS_POSSIBLE,
    CLASS_STRONG,
    CLASS_CONFIRMED,
    CLASS_OUT,
    PUBLISHABLE,
    classify_supplier_sector_fit,
    assert_denominator_invariant,
)


def _c(obj: str, orgao: str = "o1", day: int = 0) -> dict:
    return {
        "objeto_contrato": obj,
        "orgao_cnpj": orgao,
        "data_publicacao": (date(2024, 1, 1) + timedelta(days=day)).isoformat(),
        "uf": "SC",
    }


ENG = "execução de obra de engenharia e pavimentação asfáltica"
FOOD = "aquisição de refeições e alimentação escolar"
CLEAN = "serviço de limpeza e conservação predial"


def test_adding_irrelevant_never_increases_ratio() -> None:
    base = [_c(ENG, "a", 0), _c(ENG, "b", 200), _c(ENG, "a", 400)]
    d0 = classify_supplier_sector_fit(razao_social="X LTDA", contracts=base)
    d1 = classify_supplier_sector_fit(
        razao_social="X LTDA",
        contracts=base + [_c(FOOD, "f", 10)],
    )
    assert d1.relevant_contract_count == d0.relevant_contract_count
    assert d1.relevant_contract_ratio_full_history <= d0.relevant_contract_ratio_full_history
    assert_denominator_invariant(d0)
    assert_denominator_invariant(d1)


def test_removing_relevant_never_increases_count() -> None:
    base = [_c(ENG, "a", 0), _c(ENG, "b", 200), _c(FOOD, "f", 10)]
    d0 = classify_supplier_sector_fit(razao_social="X LTDA", contracts=base)
    d1 = classify_supplier_sector_fit(razao_social="X LTDA", contracts=base[1:])
    assert d1.relevant_contract_count <= d0.relevant_contract_count


def test_single_contract_without_cnae_never_strong() -> None:
    d = classify_supplier_sector_fit(
        razao_social="Y LTDA",
        contracts=[_c(ENG)],
    )
    assert d.classification not in (CLASS_STRONG, CLASS_CONFIRMED)
    assert d.classification == CLASS_POSSIBLE or d.classification not in PUBLISHABLE


def test_conflicting_name_cnae_not_publishable() -> None:
    d = classify_supplier_sector_fit(
        razao_social="Z ENGENHARIA LTDA",
        cnae_principal="4711-3/01",  # varejo
        contracts=[_c(FOOD), _c(FOOD)],
    )
    assert d.classification not in PUBLISHABLE


def test_missing_cnae_not_treated_as_positive() -> None:
    d = classify_supplier_sector_fit(
        razao_social="SEM CNAE LTDA",
        cnae_principal=None,
        contracts=[_c(CLEAN)],
    )
    assert d.classification != CLASS_CONFIRMED
    assert "cnae_principal_engineering" not in d.reason_codes


def test_out_of_scope_not_publishable() -> None:
    d = classify_supplier_sector_fit(
        razao_social="CHURRASCARIA BOI LTDA",
        contracts=[_c(FOOD)],
    )
    assert d.classification == CLASS_OUT
    assert not d.publishable


def test_row_order_does_not_change_classification() -> None:
    rows = [
        _c(ENG, "a", 0),
        _c(FOOD, "f", 10),
        _c(ENG, "b", 200),
        _c(CLEAN, "c", 50),
        _c(ENG, "a", 400),
    ]
    d1 = classify_supplier_sector_fit(razao_social="ORD LTDA", contracts=rows)
    d2 = classify_supplier_sector_fit(razao_social="ORD LTDA", contracts=list(reversed(rows)))
    assert d1.classification == d2.classification
    assert d1.relevant_contract_count == d2.relevant_contract_count
    assert d1.relevant_contract_ratio_full_history == d2.relevant_contract_ratio_full_history


def test_duplicates_counted_before_dedup_consistency() -> None:
    """Duplicate identical contracts increase total and relevant equally → ratio stable."""
    one = [_c(ENG, "a", 0)]
    dup = one + one
    d1 = classify_supplier_sector_fit(razao_social="DUP LTDA", contracts=one)
    d2 = classify_supplier_sector_fit(razao_social="DUP LTDA", contracts=dup)
    assert d2.total_contract_count_full_history == 2
    assert d2.relevant_contract_count == 2
    assert d1.relevant_contract_ratio_full_history == d2.relevant_contract_ratio_full_history


def test_missing_data_not_zero_favorable() -> None:
    d = classify_supplier_sector_fit(razao_social="EMPTY LTDA", contracts=[])
    assert d.relevant_contract_ratio_full_history == 0.0
    assert d.classification not in PUBLISHABLE


def test_incomplete_history_flag_caps_strong() -> None:
    """If history_is_full=False, contract concentration cannot yield STRONG."""
    rows = [
        _c(ENG, "a", 0),
        _c(ENG, "b", 200),
        _c(ENG, "a", 400),
        _c(ENG, "b", 500),
    ]
    d = classify_supplier_sector_fit(
        razao_social="CONSTRUTORA FULL LTDA",
        contracts=rows,
        history_is_full=False,
    )
    assert d.classification != CLASS_STRONG
    assert d.classification not in PUBLISHABLE

