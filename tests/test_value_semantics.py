"""Unit tests for scripts.lib.value_semantics — DoD §13.1 Semântica de valores."""
from __future__ import annotations

import pytest

from scripts.lib.value_semantics import (
    SOURCE_VALUE_TYPES,
    VALOR_SEMANTICA_LABELS,
    ValorSemantica,
    aggregate_contract_values,
    calculate_desagio,
    compute_bid_contract_desagio,
)


def test_source_value_types_pncp_not_preco_praticado() -> None:
    assert SOURCE_VALUE_TYPES["pncp"]["bids"] is ValorSemantica.ESTIMADO
    assert SOURCE_VALUE_TYPES["pncp"]["contracts"] is ValorSemantica.CONTRATADO
    assert SOURCE_VALUE_TYPES["pncp"]["contracts"] is not ValorSemantica.PAGO
    assert SOURCE_VALUE_TYPES["pncp"]["contracts"] is not ValorSemantica.GLOBAL


def test_labels_cover_all_enum() -> None:
    for item in ValorSemantica:
        assert item in VALOR_SEMANTICA_LABELS
        assert VALOR_SEMANTICA_LABELS[item]


def test_calculate_desagio_happy_path() -> None:
    result = calculate_desagio(1_000_000.0, 850_000.0)
    assert result is not None
    assert result["desagio_percentual"] == 15.0
    assert result["desconto_absoluto"] == 150_000.0
    assert result["semantica"] == "estimado→contratado"


def test_calculate_desagio_invalid_returns_none() -> None:
    assert calculate_desagio(0, 100) is None
    assert calculate_desagio(100, 0) is None
    assert calculate_desagio(-1, 10) is None


def test_compute_bid_contract_desagio() -> None:
    result = compute_bid_contract_desagio(200_000.0, 180_000.0)
    assert result is not None
    assert result["desagio_percentual"] == 10.0
    assert result["semantica"] == "estimado→contratado"


def test_aggregate_contract_values() -> None:
    contracts = [
        {"valor_global": 100.0},
        {"valor_global": 200.0},
        {"valor_global": None},
        {"valor_global": 0},
    ]
    agg = aggregate_contract_values(contracts)
    assert agg["count"] == 2
    assert agg["total"] == 300.0
    assert agg["min"] == 100.0
    assert agg["max"] == 200.0


@pytest.mark.unit
def test_desagio_requires_comparable_semantics() -> None:
    """DoD §25: deságio only when comparable stages are used."""
    d = calculate_desagio(500.0, 400.0, semantica="estimado→homologado")
    assert d is not None
    assert "estimado" in d["semantica"]
