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
    assert k.typology in {"cbuq_asfalto", "pavimentacao_generica", "pavimentacao"}
    assert k.comparison_confidence >= 0.5


def test_cbuq_and_paralelepipedo_are_distinct_groups():
    a = comparison_key_for_object(
        "Pavimentação Asfáltica em CBUQ de 122132 m2 em vias urbanas",
        archetype="pavimentacao-infraestrutura-viaria",
        uf="PI",
    )
    b = comparison_key_for_object(
        "Execução de pavimentação em paralelepípedos de pedra irregular",
        archetype="pavimentacao-infraestrutura-viaria",
        uf="PI",
    )
    assert a.typology == "cbuq_asfalto"
    assert b.typology == "paralelepipedo"
    assert a.comparison_group != b.comparison_group


def test_mixed_pavement_materials_not_published():
    from types import SimpleNamespace

    contracts = []
    for i in range(8):
        contracts.append(
            SimpleNamespace(
                objeto="Pavimentação Asfáltica em CBUQ de vias urbanas do município",
                valor=1_000_000 + i * 1000,
                uf="PI",
                archetypes=["pavimentacao-infraestrutura-viaria"],
                orgao_nome=f"Pref {i}",
                municipio="X",
                data_publicacao="2026-01-15",
                source="pncp",
                contrato_id=f"cbuq{i}",
            )
        )
    for i in range(8):
        contracts.append(
            SimpleNamespace(
                objeto="Execução de pavimentação em paralelepípedos nas vias municipais",
                valor=500_000 + i * 1000,
                uf="PI",
                archetypes=["pavimentacao-infraestrutura-viaria"],
                orgao_nome=f"PrefB {i}",
                municipio="Y",
                data_publicacao="2026-01-15",
                source="pncp",
                contrato_id=f"par{i}",
            )
        )
    prices = build_comparable_prices(contracts, min_obs=8)
    # Must not publish a single mixed group with both materials
    for p in prices:
        objs = " ".join(e["objeto"].lower() for e in p.get("public_examples") or [])
        has_cbuq = "cbuq" in objs or "asfáltica" in objs or "asfaltica" in objs
        has_par = "paralelep" in objs
        assert not (has_cbuq and has_par), p.get("comparison_group")


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
