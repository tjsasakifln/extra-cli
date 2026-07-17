"""Unit tests for deterministic procurement act classifier."""

from __future__ import annotations

from scripts.crawl.act_classifier import ALL_CATEGORIES, classify_act


def test_categories_include_required_set():
    required = {
        "aviso_licitacao",
        "edital",
        "retificacao",
        "suspensao",
        "revogacao",
        "anulacao",
        "homologacao",
        "adjudicacao",
        "extrato_contrato",
        "termo_aditivo",
        "rescisao",
        "ata_registro_precos",
        "dispensa",
        "inexigibilidade",
        "credenciamento",
        "intencao_registro_precos",
        "outros",
    }
    assert required.issubset(set(ALL_CATEGORIES))


def test_classifies_homologacao():
    r = classify_act("Homologação do Pregão Eletrônico nº 12/2026")
    assert r["category"] == "homologacao"
    assert r["confidence"] == "high"


def test_classifies_termo_aditivo():
    r = classify_act("Extrato de Termo Aditivo ao Contrato 45/2025")
    assert r["category"] == "termo_aditivo"


def test_classifies_ata_rp():
    r = classify_act("Ata de Registro de Preços nº 3/2026 - material de construção")
    assert r["category"] == "ata_registro_precos"


def test_classifies_dispensa():
    r = classify_act("Aviso de dispensa de licitação por valor")
    assert r["category"] == "dispensa"


def test_unknown_is_outros():
    r = classify_act("Comunicado interno de férias coletivas")
    assert r["category"] == "outros"
    assert r["confidence"] == "low"
