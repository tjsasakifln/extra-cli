"""Engineering object matcher — no mão-de-obra / materials false positives."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.public_agency.signals import is_engineering_object
from scripts.public_agency.fragmentation import assess_fragmentation, _same_nature
from scripts.public_agency.pipeline import run_public_agency_pipeline


def test_mao_de_obra_is_not_engineering():
    assert is_engineering_object("Contratação de mão de obra temporária para limpeza") is False
    assert is_engineering_object("MÃO DE OBRA PARA SERVIÇOS GERAIS") is False
    assert is_engineering_object("mao-de-obra especializada em cabelo e maquiagem") is False


def test_pageant_hair_makeup_not_engineering():
    obj = (
        "CONTRATAÇÃO DE EMPRESA ESPECIALIZADA EM SERVIÇOS DE CABELO, MAQUIAGEM E BELEZA "
        "PARA CONCURSO MUNICIPAL — INCLUI MÃO DE OBRA"
    )
    assert is_engineering_object(obj) is False


def test_materials_only_not_engineering():
    assert is_engineering_object("AQUISIÇÃO DE MATERIAIS DE CONSTRUÇÃO DIVERSOS") is False
    assert is_engineering_object("FORNECIMENTO DE MATERIAIS ELÉTRICOS PARA EDIFICAÇÕES") is False
    assert is_engineering_object("COMPRA DE PNEUS E CÂMARAS DE AR") is False


def test_real_engineering_still_matches():
    assert is_engineering_object("Obra de pavimentação asfáltica e drenagem urbana") is True
    assert is_engineering_object("Execução de obras de saneamento e rede de esgoto") is True
    assert is_engineering_object("Elaboração de projeto básico de engenharia civil") is True
    assert is_engineering_object("Reforma de escola municipal — engenharia e construção") is True
    assert is_engineering_object("Serviços técnicos de engenharia para fiscalização de obra") is True


def test_fragmentation_does_not_flag_mixed_non_eng_contracts():
    # Mixed buyer history: tires, chairs, paper — not same-nature engineering
    frag = assess_fragmentation(
        proposed_amount=None,
        ceiling=130984.20,
        same_nature_contracts=[
            {"amount": 10000, "object": "aquisição de pneus", "id": "1"},
            {"amount": 5000, "object": "cadeiras escolares", "id": "2"},
            {"amount": 3000, "object": "papel A4 e material de expediente", "id": "3"},
        ],
        complete_annual_ledger=False,
    )
    assert "recurring_same_nature_contracting" not in frag.indicators
    # When caller incorrectly passes non-eng as same_nature, pairwise check should not fire
    assert not _same_nature("pneus", "cadeiras")


def test_pipeline_rejects_pageant_as_material_engineering_need(tmp_path: Path):
    rows = [
        {
            "contrato_id": "p1",
            "orgao_cnpj": "83102373000199",
            "orgao_nome": "PREFEITURA MUNICIPAL DE PALMITOS - SC",
            "objeto_contrato": (
                "CONTRATAÇÃO DE SERVIÇOS DE CABELO E MAQUIAGEM COM MÃO DE OBRA "
                "PARA CONCURSO DE BELEZA MUNICIPAL"
            ),
            "valor_total": 15000,
            "data_publicacao": "2026-01-10",
            "data_inicio": "2026-01-15",
            "data_fim": "2026-06-30",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "p2",
            "orgao_cnpj": "83102373000199",
            "orgao_nome": "PREFEITURA MUNICIPAL DE PALMITOS - SC",
            "objeto_contrato": "Aquisição de materiais de construção diversos",
            "valor_total": 20000,
            "data_publicacao": "2025-06-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "p3",
            "orgao_cnpj": "83102373000199",
            "orgao_nome": "PREFEITURA MUNICIPAL DE PALMITOS - SC",
            "objeto_contrato": "Fornecimento de pneus para frota municipal",
            "valor_total": 8000,
            "data_publicacao": "2025-03-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
    ]
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "pageant",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    # Should not publish on material engineering need alone
    names = [L["agency"]["nome_oficial"] for L in r.get("leads") or []]
    assert not any("PALMITOS" in n.upper() for n in names), (
        f"pageant/materials-only Palmitos must not be PUBLISHABLE, got {names}"
    )


def test_pipeline_still_publishes_real_pavement_recurring(tmp_path: Path):
    rows = [
        {
            "contrato_id": f"e{i}",
            "orgao_cnpj": "83102373000100",
            "orgao_nome": "PREFEITURA MUNICIPAL DE JUPIÁ",
            "objeto_contrato": obj,
            "valor_total": 40000,
            "data_publicacao": pub,
            "data_inicio": "2025-01-01",
            "data_fim": "2026-12-31",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        }
        for i, (obj, pub) in enumerate(
            [
                ("Obra de pavimentação asfáltica trecho norte", "2025-03-01"),
                ("Obra de pavimentação e drenagem trecho sul", "2025-08-01"),
                ("Serviços de engenharia para acompanhamento de obra de pavimentação", "2026-01-15"),
            ],
            start=1,
        )
    ]
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "pav",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    assert r["status"] == "PASS"
    assert r["leads"], "real engineering recurring works must remain publishable"
    lead = r["leads"][0]
    fired = {s["signal_id"] for s in lead["signals"] if s["status"] == "FIRED"}
    assert "recurring_engineering_procurements" in fired or lead["score"]["need_score"] >= 0.35
