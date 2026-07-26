"""All-status supplier history vs active commercial portfolio separation."""

from __future__ import annotations

from datetime import date, timedelta

from scripts.commercial_leads import HISTORY_VIEW_ACTIVE_PORTFOLIO, HISTORY_VIEW_ALL_SNAPSHOT
from scripts.commercial_leads.pipeline import (
    compute_supplier_history_metrics,
    split_history_views,
)
from scripts.commercial_leads.sector_fit import (
    CLASS_CONFLICTING,
    CLASS_OUT,
    CLASS_STRONG,
    PUBLISHABLE,
    classify_supplier_sector_fit,
)


def _c(
    obj: str,
    *,
    active: bool = True,
    orgao: str = "org-1",
    pub: date | None = None,
) -> dict:
    return {
        "objeto_contrato": obj,
        "is_active": active,
        "orgao_cnpj": orgao,
        "orgao_nome": orgao,
        "data_publicacao": (pub or date(2025, 1, 15)).isoformat(),
        "uf": "SC",
    }


def test_split_views_and_invariants() -> None:
    rows = [
        _c("execução de obras de engenharia", active=True),
        _c("fornecimento de merenda escolar", active=False),
        _c("limpeza predial", active=False),
    ]
    all_h, active = split_history_views(rows)
    assert len(all_h) == 3
    assert len(active) == 1
    m = compute_supplier_history_metrics(rows)
    assert m["history_view_all"] == HISTORY_VIEW_ALL_SNAPSHOT
    assert m["history_view_active"] == HISTORY_VIEW_ACTIVE_PORTFOLIO
    assert m["all_snapshot_contract_count"] == 3
    assert m["active_contract_count"] == 1
    assert m["inactive_or_closed_contract_count"] == 2
    assert m["invariant_active_plus_inactive"] is True
    assert m["invariant_relevance_partition"] is True
    assert (
        m["relevant_all_history_count"]
        + m["irrelevant_all_history_count"]
        + m["review_all_history_count"]
        == m["all_snapshot_contract_count"]
    )


def test_adversarial_one_active_relevant_nine_closed_food() -> None:
    """1 active relevant + 9 closed food → ratio 0.10; never STRONG by active concentration."""
    rows = [_c("execução de obras e serviços de engenharia civil", active=True, orgao="a")]
    for i in range(9):
        rows.append(
            _c(
                "fornecimento de alimentação escolar e merenda",
                active=False,
                orgao=f"food-{i}",
                pub=date(2024, 1, 1) + timedelta(days=i * 30),
            )
        )
    m = compute_supplier_history_metrics(rows)
    assert m["all_snapshot_contract_count"] == 10
    assert m["relevant_all_history_ratio"] == 0.1
    assert m["active_relevant_ratio"] == 1.0
    d = classify_supplier_sector_fit(
        razao_social="FORNECEDORA MISTA LTDA",
        contracts=rows,
        history_is_full=True,
    )
    # Must not be STRONG from active-only concentration
    assert d.classification != CLASS_STRONG
    assert d.relevant_contract_ratio_full_history == 0.1
    assert d.classification not in PUBLISHABLE or d.classification != CLASS_STRONG


def test_adversarial_active_eng_historical_materials() -> None:
    """3 active eng + 20 historical materials commerce → CONFLICTING or OUT_OF_SCOPE."""
    rows = []
    for i in range(3):
        rows.append(
            _c(
                "execução de obras e serviços de engenharia para estradas",
                active=True,
                orgao=f"eng-{i}",
                pub=date(2025, 1, 1) + timedelta(days=i * 10),
            )
        )
    for i in range(20):
        rows.append(
            _c(
                "fornecimento de materiais de construção e artefatos de cimento",
                active=False,
                orgao=f"mat-{i}",
                pub=date(2023, 1, 1) + timedelta(days=i * 20),
            )
        )
    d = classify_supplier_sector_fit(
        razao_social="COMERCIO DE MATERIAIS E OBRAS LTDA",
        contracts=rows,
        cnae_principal="4744-0/99 - Comércio varejista de materiais de construção",
        history_is_full=True,
    )
    assert d.classification in {CLASS_OUT, CLASS_CONFLICTING}
    m = compute_supplier_history_metrics(rows)
    assert m["all_snapshot_contract_count"] == 23
    assert m["active_contract_count"] == 3
    # Historical materials dominate all-history ratio
    assert m["relevant_all_history_ratio"] < m["active_relevant_ratio"]


def test_active_portfolio_not_historical_denominator() -> None:
    """Active-only view must not be used as sector denominator."""
    rows = [
        _c("pavimentação asfáltica", active=True),
        _c("fornecimento de merenda", active=False),
        _c("limpeza de vias", active=False),
    ]
    m = compute_supplier_history_metrics(rows)
    # If someone wrongly used active-only, ratio would be 1.0
    assert m["active_relevant_ratio"] == 1.0
    assert m["relevant_all_history_ratio"] < 1.0
    d = classify_supplier_sector_fit(
        razao_social="EMPRESA X",
        contracts=rows,
        history_is_full=True,
    )
    # Denominator must be 3 not 1
    assert d.total_contract_count_full_history == 3


def test_loader_sql_does_not_filter_is_active_by_default() -> None:
    """Source inspection: default load path must not hardcode active-only for sector history."""
    import inspect

    from scripts.commercial_leads import pipeline as pl

    src = inspect.getsource(pl.load_full_supplier_histories)
    assert "active_only" in src
    # Default path builds SQL without forcing is_active unless active_only
    assert "if active_only:" in src
    assert "ALL_SNAPSHOT" in src or "HISTORY_VIEW_ALL_SNAPSHOT" in src
