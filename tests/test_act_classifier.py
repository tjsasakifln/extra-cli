"""Unit tests for deterministic procurement act classifier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.crawl.act_classifier import (
    ALL_CATEGORIES,
    CORE_CATEGORIES,
    classify_act,
    classify_many,
    classify_record,
)

CORPUS_PATH = Path(__file__).parent / "fixtures" / "act_classifier_corpus.json"

REQUIRED_CATEGORIES = {
    "aviso_licitacao",
    "edital",
    "retificacao",
    "errata",
    "suspensao",
    "reabertura",
    "revogacao",
    "anulacao",
    "homologacao",
    "adjudicacao",
    "resultado",
    "extrato_contrato",
    "termo_aditivo",
    "apostilamento",
    "rescisao",
    "ata_registro_precos",
    "intencao_registro_precos",
    "dispensa",
    "inexigibilidade",
    "credenciamento",
    "chamamento_publico",
    "consulta_publica",
    "outros_atos_contratacao",
    "nao_relacionado",
    "outros",
}


def _load_corpus() -> list[dict]:
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return data["cases"]


# ---------------------------------------------------------------------------
# Category inventory
# ---------------------------------------------------------------------------


def test_categories_include_required_set():
    assert REQUIRED_CATEGORIES.issubset(set(ALL_CATEGORIES))
    assert set(CORE_CATEGORIES) == set(ALL_CATEGORIES)


def test_output_schema_keys():
    r = classify_act("Homologação do Pregão Eletrônico nº 12/2026")
    for key in (
        "category",
        "confidence",
        "confidence_label",
        "rules_fired",
        "terms_found",
        "reason",
        "needs_human_review",
        "matched_rule",
        "evidence",
    ):
        assert key in r
    assert isinstance(r["confidence"], float)
    assert 0.0 <= r["confidence"] <= 1.0
    assert r["confidence_label"] in {"high", "medium", "low"}
    assert isinstance(r["rules_fired"], list)
    assert isinstance(r["terms_found"], list)
    assert isinstance(r["reason"], str)
    assert isinstance(r["needs_human_review"], bool)


# ---------------------------------------------------------------------------
# Core single-field cases (legacy smoke)
# ---------------------------------------------------------------------------


def test_classifies_homologacao():
    r = classify_act("Homologação do Pregão Eletrônico nº 12/2026")
    assert r["category"] == "homologacao"
    assert r["confidence_label"] == "high"
    assert r["confidence"] >= 0.8
    assert r["rules_fired"]


def test_classifies_termo_aditivo():
    r = classify_act("Extrato de Termo Aditivo ao Contrato 45/2025")
    assert r["category"] == "termo_aditivo"


def test_classifies_ata_rp():
    r = classify_act("Ata de Registro de Preços nº 3/2026 - material de construção")
    assert r["category"] == "ata_registro_precos"


def test_classifies_dispensa():
    r = classify_act("Aviso de dispensa de licitação por valor")
    assert r["category"] == "dispensa"


def test_unknown_is_outros_or_nao_relacionado():
    r = classify_act("Comunicado interno de férias coletivas")
    assert r["category"] in {"outros", "nao_relacionado"}
    assert r["confidence_label"] in {"low", "high", "medium"}
    assert r["needs_human_review"] is True or r["category"] == "nao_relacionado"


def test_empty_text():
    r = classify_act("")
    assert r["category"] == "outros"
    assert r["needs_human_review"] is True
    assert r["confidence"] < 0.3


# ---------------------------------------------------------------------------
# Multi-field + priority
# ---------------------------------------------------------------------------


def test_title_overrides_body_noise():
    r = classify_act(
        "Texto genérico sem palavras-chave relevantes no corpo.",
        title="Homologação do Pregão Eletrônico nº 99/2026",
    )
    assert r["category"] == "homologacao"
    assert r["confidence"] >= 0.7


def test_official_type_helps():
    r = classify_act(
        "Publicação referente ao processo administrativo.",
        official_type="Dispensa de Licitação",
        title="Contratação de serviços de impressão",
    )
    assert r["category"] == "dispensa"


def test_termo_aditivo_beats_extrato_contrato():
    r = classify_act("Extrato de Termo Aditivo ao Contrato nº 10/2023")
    assert r["category"] == "termo_aditivo"


def test_errata_separate_from_retificacao():
    r = classify_act("Errata ao Edital de Concorrência nº 02/2026")
    assert r["category"] == "errata"


def test_retificacao_requires_procurement_context():
    r = classify_act("Retificação do Edital do Pregão Eletrônico nº 09/2026")
    assert r["category"] == "retificacao"


def test_suspensao_without_procurement_not_forced():
    # "suspensão de férias" alone should not become suspensao de licitação
    r = classify_act("Suspensão de férias do servidor João — setor de RH")
    assert r["category"] != "suspensao"


def test_negative_nomeacao():
    r = classify_act("Nomeação de servidor para cargo em comissão")
    assert r["category"] == "nao_relacionado"
    assert any("neg:" in x or "nomeacao" in x for x in r["rules_fired"]) or r["matched_rule"]


def test_concurso_publico_nao_relacionado():
    r = classify_act(
        "Abre inscrições para concurso público de provimento de cargos.",
        title="Edital de Concurso Público nº 01/2026",
    )
    assert r["category"] == "nao_relacionado"


def test_chamamento_publico_not_aviso():
    r = classify_act("Chamamento Público nº 01/2026 — Organizações da Sociedade Civil")
    assert r["category"] == "chamamento_publico"


def test_consulta_publica():
    r = classify_act("Consulta Pública — minuta de edital de concorrência")
    assert r["category"] == "consulta_publica"


def test_apostilamento():
    r = classify_act("Apostilamento ao Contrato nº 08/2025 — reajuste IPCA")
    assert r["category"] == "apostilamento"


def test_intencao_rp():
    r = classify_act("Intenção de Registro de Preços — IRP nº 05/2026")
    assert r["category"] == "intencao_registro_precos"


def test_reabertura():
    r = classify_act("Reabertura de prazo — Pregão Eletrônico nº 07/2026")
    assert r["category"] == "reabertura"


def test_number_patterns_boost_terms():
    r = classify_act("Homologação do Pregão Eletrônico nº 12/2026, Contrato nº 1/2026")
    assert "num_pregao" in r["terms_found"] or any("preg" in t for t in r["terms_found"])


def test_secondary_param_still_works():
    r = classify_act("Publicação oficial", secondary="Homologação do certame Pregão Eletrônico nº 1/2026")
    assert r["category"] == "homologacao"


def test_classify_many():
    results = classify_many(
        [
            "Homologação do Pregão Eletrônico nº 1/2026",
            "Ata de Registro de Preços nº 2/2026",
        ]
    )
    assert len(results) == 2
    assert results[0]["category"] == "homologacao"
    assert results[1]["category"] == "ata_registro_precos"


def test_classify_record_dict():
    r = classify_record(
        {
            "titulo": "Extrato de Contrato nº 45/2026",
            "texto": "Contrato administrativo para fornecimento de materiais.",
            "tipo": "Contrato",
        }
    )
    assert r["category"] == "extrato_contrato"


def test_homologacao_preferred_over_adjudicacao_when_both():
    r = classify_act("Homologação e Adjudicação do Pregão nº 05/2026")
    assert r["category"] == "homologacao"
    # Ambiguity should surface for human assist
    assert r["needs_human_review"] is True or "adjudic" in " ".join(r["rules_fired"]).lower()


def test_outros_atos_designacao_pregoeiro():
    r = classify_act("Designação de pregoeiro e equipe de apoio para o Pregão Eletrônico nº 11/2026")
    assert r["category"] == "outros_atos_contratacao"


# ---------------------------------------------------------------------------
# Corpus regression (≥25 real-like sanitized cases)
# ---------------------------------------------------------------------------


def test_corpus_has_at_least_25_cases():
    cases = _load_corpus()
    assert len(cases) >= 25


def test_corpus_covers_major_categories():
    cases = _load_corpus()
    expected_set = {c["expected"] for c in cases}
    major = {
        "aviso_licitacao",
        "edital",
        "homologacao",
        "termo_aditivo",
        "extrato_contrato",
        "dispensa",
        "ata_registro_precos",
        "nao_relacionado",
        "errata",
        "suspensao",
        "revogacao",
        "rescisao",
    }
    missing = major - expected_set
    assert not missing, f"corpus missing major categories: {missing}"


@pytest.mark.parametrize("case", _load_corpus(), ids=lambda c: c["id"])
def test_corpus_case(case: dict):
    r = classify_act(
        case.get("text") or case.get("title") or "",
        title=case.get("title"),
        subject=case.get("subject"),
        official_type=case.get("official_type"),
        category=case.get("category"),
        secondary=case.get("secondary"),
    )
    assert r["category"] == case["expected"], (
        f"{case['id']}: got {r['category']} expected {case['expected']} "
        f"(reason={r['reason']!r}, rules={r['rules_fired']})"
    )
