"""Benchmark comparability gates."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.pseo.comparison import build_comparable_prices, comparison_key_for_object


def test_locacao_low_confidence():
    k = comparison_key_for_object("Locação de imóvel para secretaria municipal", uf="SC")
    assert k.nature == "locacao"
    assert k.comparison_confidence < 0.3


def test_pavimentacao_group():
    k = comparison_key_for_object(
        "Execução de obra de pavimentação asfáltica em vias urbanas",
        archetype="pavimentacao-infraestrutura-viaria",
        uf="SC",
    )
    assert k.typology == "pavimentacao"
    assert "pavimentacao" in k.comparison_group
    assert k.comparison_confidence >= 0.5


def test_build_prices_rejects_mixed_nature():
    contracts = []
    for i in range(15):
        contracts.append(
            SimpleNamespace(
                objeto="Execução de obra de pavimentação asfáltica em vias urbanas do município",
                valor=500_000 + i * 1000,
                uf="SC",
                archetypes=["pavimentacao-infraestrutura-viaria"],
                orgao_nome=f"Pref {i}",
                municipio="X",
                data_publicacao="2026-01-15",
                source="pncp",
                contrato_id=f"c{i}",
            )
        )
    # inject locacao — should not enter comparable group with works
    contracts.append(
        SimpleNamespace(
            objeto="Locação de imóvel para funcionamento de órgão",
            valor=100_000,
            uf="SC",
            archetypes=["pavimentacao-infraestrutura-viaria"],  # wrongly labeled in bad pipeline
            orgao_nome="Y",
            municipio="Y",
            data_publicacao="2026-01-15",
            source="pncp",
            contrato_id="bad",
        )
    )
    prices = build_comparable_prices(contracts, min_obs=12)
    assert prices
    for p in prices:
        assert p["comparison_confidence"] >= 0.55
        objs = " ".join(e["objeto"] for e in p["public_examples"])
        assert "Locação" not in objs or p.get("heterogeneity_flags")
