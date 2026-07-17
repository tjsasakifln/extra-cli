"""Tests for commercial status classifier and sector filter."""

from __future__ import annotations

from datetime import date, timedelta

from scripts.coverage.commercial_status import classify_commercial
from scripts.coverage.sector_engineering import classify_sector


def test_open_by_deadline():
    today = date(2026, 7, 17)
    r = classify_commercial(
        title="Pregão Eletrônico 10/2026",
        official_status="Em Recebimento de Proposta",
        data_encerramento=today + timedelta(days=5),
        as_of=today,
    )
    assert r.status == "OPEN_OPPORTUNITY"
    assert r.confidence >= 0.85


def test_closed_deadline_passed():
    today = date(2026, 7, 17)
    r = classify_commercial(
        title="Pregão 1/2026",
        data_encerramento=today - timedelta(days=1),
        as_of=today,
    )
    assert r.status == "CLOSED"
    assert "deadline_passed" in r.rules_fired


def test_homologado_is_result_not_open():
    r = classify_commercial(
        title="Obra de pavimentação",
        official_status="Homologado",
        as_of=date(2026, 7, 17),
    )
    assert r.status == "RESULT"
    assert r.status != "OPEN_OPPORTUNITY"


def test_publicado_resultado_is_not_open():
    """Regression: bare 'publicado' must not open-classify result publications."""
    r = classify_commercial(
        title="Pavimentação asfáltica",
        official_status="Publicado Resultado da Licitação",
        as_of=date(2026, 7, 17),
    )
    assert r.status == "RESULT"
    assert r.status != "OPEN_OPPORTUNITY"


def test_bare_publicado_is_not_open():
    r = classify_commercial(
        title="Contratação de serviços",
        official_status="Publicado",
        as_of=date(2026, 7, 17),
    )
    assert r.status != "OPEN_OPPORTUNITY"


def test_ciga_edital_recent_notice():
    today = date(2026, 7, 17)
    r = classify_commercial(
        act_category="edital",
        title="EDITAL DE PREGÃO ELETRÔNICO Nº 12/2026",
        data_publicacao=today - timedelta(days=3),
        as_of=today,
    )
    assert r.status == "RECENT_NOTICE"


def test_nao_relacionado():
    r = classify_commercial(
        act_category="nao_relacionado",
        title="Portaria de nomeação de servidor",
        as_of=date(2026, 7, 17),
    )
    assert r.status == "NOT_RELEVANT"


def test_sector_pavimentacao():
    s = classify_sector("Contratação de empresa para pavimentação asfáltica de vias urbanas")
    assert s.sector_match is True
    assert s.sector == "pavimentacao"
    assert "pavimentacao" in s.terms or "asfalto" in s.terms


def test_sector_false_positive_software():
    s = classify_sector(
        "Contratação de serviços de sustentação e licenciamento de softwares de telefonia IP"
    )
    assert s.sector_match is False or s.score < 0.35
    assert "ti_software" in s.negative_hits or s.sector_match is False


def test_sector_generic_servico_alone():
    s = classify_sector("Prestação de serviços diversos para o município")
    assert s.sector_match is False
