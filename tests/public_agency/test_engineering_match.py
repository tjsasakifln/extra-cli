"""Golden corpus + pipeline seals for multi-tier engineering object classifier."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.public_agency.fragmentation import _same_nature, assess_fragmentation
from scripts.public_agency.pipeline import run_public_agency_pipeline
from scripts.public_agency.signals import (
    TIER_HARD_NEGATIVE,
    TIER_STRONG_WORKS,
    classify_engineering_object,
    is_engineering_object,
)

_CORPUS = Path(__file__).resolve().parent / "fixtures" / "engineering_object_corpus.jsonl"


def _load_corpus() -> list[dict]:
    rows = []
    for line in _CORPUS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


@pytest.mark.parametrize("row", _load_corpus(), ids=lambda r: r["id"])
def test_engineering_object_corpus(row: dict) -> None:
    verdict = classify_engineering_object(row["obj"])
    assert verdict.is_engineering is row["expect_engineering"], (
        f"{row['id']}: expected eng={row['expect_engineering']} got {verdict}"
    )
    assert verdict.tier == row["expect_tier"], (
        f"{row['id']}: expected tier={row['expect_tier']} got {verdict.tier} reasons={verdict.reasons}"
    )
    # Boolean API must agree with STRONG_WORKS only
    assert is_engineering_object(row["obj"]) is (row["expect_tier"] == TIER_STRONG_WORKS)


def test_profile_keywords_never_alone_force_true() -> None:
    # Without keywords: acquisition for infrastructure secretariat is not eng
    obj = "AQUISIÇÃO DE ROMPEDOR HIDRÁULICO PARA A SECRETARIA MUNICIPAL DE INFRAESTRUTURA"
    assert is_engineering_object(obj) is False
    # With profile keywords that short-circuited the old matcher:
    kws = ["infraestrutura", "edificacao", "construção", "obra", "engenharia"]
    v = classify_engineering_object(obj, kws)
    assert v.is_engineering is False
    assert v.tier == TIER_HARD_NEGATIVE


def test_xanxere_concessao_not_engineering() -> None:
    obj = (
        "CONCESSÃO DE USO DE BEM PÚBLICO — ÁREA COM EDIFICAÇÃO DE 749,76 M², "
        "CANCHA DE BOCHA E ESTACIONAMENTO"
    )
    v = classify_engineering_object(obj)
    assert v.is_engineering is False
    assert v.tier == TIER_HARD_NEGATIVE
    assert any("occupancy" in r or "concessao" in r for r in v.reasons) or "occupancy_concessao" in v.reasons


def test_fragmentation_mixed_compras_not_same_nature() -> None:
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
    assert not _same_nature("pneus", "cadeiras")


def test_pipeline_xanxere_like_not_publishable(tmp_path: Path) -> None:
    rows = [
        {
            "contrato_id": "x1",
            "orgao_cnpj": "83102000000199",
            "orgao_nome": "MUNICÍPIO DE XANXERÊ",
            "objeto_contrato": (
                "CONCESSÃO DE USO DE BEM PÚBLICO — ÁREA COM EDIFICAÇÃO DE 749,76 M², "
                "CANCHA DE BOCHA E ESTACIONAMENTO"
            ),
            "valor_total": 50000,
            "data_publicacao": "2026-01-10",
            "data_inicio": "2025-01-01",
            "data_fim": "2026-12-31",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "x2",
            "orgao_cnpj": "83102000000199",
            "orgao_nome": "MUNICÍPIO DE XANXERÊ",
            "objeto_contrato": "AQUISIÇÃO DE MATERIAIS DE EXPEDIENTE",
            "valor_total": 2000,
            "data_publicacao": "2025-06-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "x3",
            "orgao_cnpj": "83102000000199",
            "orgao_nome": "MUNICÍPIO DE XANXERÊ",
            "objeto_contrato": "COMPRA DE PNEUS PARA FROTA",
            "valor_total": 8000,
            "data_publicacao": "2025-03-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
    ]
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "xanxere",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    names = [L["agency"]["nome_oficial"] for L in r.get("leads") or []]
    assert not any("XANXER" in n.upper() for n in names), f"Xanxerê must not be PUBLISHABLE: {names}"


def test_pipeline_pageant_palmitos_not_publishable(tmp_path: Path) -> None:
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
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "p2",
            "orgao_cnpj": "83102373000199",
            "orgao_nome": "PREFEITURA MUNICIPAL DE PALMITOS - SC",
            "objeto_contrato": "AQUISIÇÃO DE MATERIAIS DE CONSTRUÇÃO DIVERSOS",
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
            "objeto_contrato": "FORNECIMENTO DE PNEUS PARA FROTA MUNICIPAL",
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
    names = [L["agency"]["nome_oficial"] for L in r.get("leads") or []]
    assert not any("PALMITOS" in n.upper() for n in names)


def test_occupancy_always_wins_over_obra_de_and_execucao() -> None:
    """Concessão/cessão never become STRONG_WORKS via soft or true works phrases."""
    cases = [
        "CONCESSÃO DE USO DE BEM PÚBLICO — OBRA DE INFRAESTRUTURA EXISTENTE NO PARQUE",
        "CONCESSÃO DE USO COM EXECUÇÃO DE OBRAS DE PAVIMENTAÇÃO",
        "CESSÃO DE IMÓVEL PÚBLICO COM EDIFICAÇÃO E OBRA DE AMPLIAÇÃO EXISTENTE",
    ]
    for obj in cases:
        v = classify_engineering_object(obj)
        assert v.is_engineering is False, obj
        assert v.tier == TIER_HARD_NEGATIVE, obj
        assert any("occupancy" in r for r in v.reasons), (obj, v.reasons)


def test_obra_de_arte_never_strong_works() -> None:
    for obj in (
        "AQUISIÇÃO DE OBRA DE ARTE CONTEMPORÂNEA PARA ACERVO DO MUSEU MUNICIPAL",
        "COMPRA DE OBRAS DE ARTE PARA EXPOSIÇÃO PERMANENTE",
        "OBRA DE ARTE PÚBLICA PARA PRAÇA CENTRAL",
    ):
        v = classify_engineering_object(obj)
        assert v.is_engineering is False, obj
        assert v.tier == TIER_HARD_NEGATIVE, (obj, v)
        assert is_engineering_object(obj) is False


def test_pipeline_occupancy_obra_de_not_publishable(tmp_path: Path) -> None:
    """Skeptic FP: occupancy + 'OBRA DE …' must not yield a public-agency lead."""
    rows = [
        {
            "contrato_id": "occ1",
            "orgao_cnpj": "83102999000111",
            "orgao_nome": "MUNICÍPIO DE SKEPTIC-OCCUPANCY",
            "objeto_contrato": (
                "CONCESSÃO DE USO DE BEM PÚBLICO — OBRA DE INFRAESTRUTURA "
                "EXISTENTE NO PARQUE MUNICIPAL"
            ),
            "valor_total": 60000,
            "data_publicacao": "2026-01-10",
            "data_inicio": "2025-01-01",
            "data_fim": "2026-12-31",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "occ2",
            "orgao_cnpj": "83102999000111",
            "orgao_nome": "MUNICÍPIO DE SKEPTIC-OCCUPANCY",
            "objeto_contrato": "CESSÃO DE IMÓVEL PÚBLICO COM EDIFICAÇÃO EXISTENTE",
            "valor_total": 25000,
            "data_publicacao": "2025-06-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "occ3",
            "orgao_cnpj": "83102999000111",
            "orgao_nome": "MUNICÍPIO DE SKEPTIC-OCCUPANCY",
            "objeto_contrato": "AQUISIÇÃO DE MATERIAIS DE EXPEDIENTE",
            "valor_total": 3000,
            "data_publicacao": "2025-03-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
    ]
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "occ",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    names = [L["agency"]["nome_oficial"] for L in r.get("leads") or []]
    assert not any("SKEPTIC-OCCUPANCY" in n.upper() for n in names), names


def test_pipeline_obra_de_arte_not_publishable(tmp_path: Path) -> None:
    """Skeptic FP: cultural 'obra de arte' must not yield a public-agency lead."""
    rows = [
        {
            "contrato_id": "art1",
            "orgao_cnpj": "83102888000122",
            "orgao_nome": "FUNDAÇÃO CULTURAL SKEPTIC-ARTE",
            "objeto_contrato": (
                "AQUISIÇÃO DE OBRA DE ARTE CONTEMPORÂNEA PARA ACERVO DO MUSEU MUNICIPAL"
            ),
            "valor_total": 45000,
            "data_publicacao": "2026-01-10",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "art2",
            "orgao_cnpj": "83102888000122",
            "orgao_nome": "FUNDAÇÃO CULTURAL SKEPTIC-ARTE",
            "objeto_contrato": "COMPRA DE OBRAS DE ARTE PARA EXPOSIÇÃO PERMANENTE",
            "valor_total": 30000,
            "data_publicacao": "2025-06-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
        {
            "contrato_id": "art3",
            "orgao_cnpj": "83102888000122",
            "orgao_nome": "FUNDAÇÃO CULTURAL SKEPTIC-ARTE",
            "objeto_contrato": "FORNECIMENTO DE MATERIAIS DE EXPEDIENTE PARA SECRETARIA",
            "valor_total": 5000,
            "data_publicacao": "2025-03-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
    ]
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "arte",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    names = [L["agency"]["nome_oficial"] for L in r.get("leads") or []]
    assert not any("SKEPTIC-ARTE" in n.upper() for n in names), names


def test_pipeline_real_pavement_still_publishable(tmp_path: Path) -> None:
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
                ("Obra de pavimentação e drenagem urbana trecho sul", "2025-08-01"),
                ("Serviços de engenharia para fiscalização de obra de pavimentação", "2026-01-15"),
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
    assert r["leads"], "real engineering recurring works must remain publishable"
    lead = r["leads"][0]
    eng_ev = [e for e in lead["evidence"] if e.get("is_engineering_object") or e.get("eng_tier") == TIER_STRONG_WORKS]
    assert eng_ev, "evidence must include STRONG_WORKS objects"
    assert lead["evidence"][0].get("eng_tier") == TIER_STRONG_WORKS or lead["evidence"][0].get(
        "is_engineering_object"
    )
