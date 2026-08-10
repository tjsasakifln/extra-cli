"""Adversarial multi-service router cases A–E (reajuste never implicit default)."""

from __future__ import annotations

from scripts.confenge_account_intelligence.catalog import load_catalog
from scripts.confenge_account_intelligence.normalize import normalize_record
from scripts.confenge_account_intelligence.router import select_services
from scripts.confenge_account_intelligence.service_distribution import (
    build_service_distribution,
    diagnose_service_monoculture,
)


def _sel(bag, structure=None, why=None):
    cat = load_catalog()
    structure = structure or {"structure_class": "unknown", "lean_signals": []}
    why = why or {"trigger": ""}
    return select_services(bag, structure=structure, why=why, catalog=cat)


def test_case_a_recent_licitacoes_not_reajuste() -> None:
    """Several new contracts / recent tenders → apoio_licitacoes_propostas."""
    bag = {
        "contracts": [
            {
                "id": f"c{i}",
                "object": f"edital de licitação obras civis lote {i}",
                "start_date": "2026-05-01",
                "age_days": 30 + i,
                "publication_date": "2026-05-01",
                "tender_or_proposal_signal": True,
                "has_reajuste": False,
            }
            for i in range(3)
        ],
        "facts": [],
        "signals": {"recent_tender_activity": True},
    }
    r = _sel(bag, why={"trigger": ""})
    assert r["primary_service"]["service_id"] == "apoio_licitacoes_propostas"
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"


def test_case_b_glosa_medicao() -> None:
    bag = {
        "contracts": [
            {
                "id": "c1",
                "object": "execução de obra com glosa em medição",
                "start_date": "2024-01-01",
                "age_days": 500,
                "glosa_signals": True,
                "measurement_issues": True,
                "has_reajuste": False,
            }
        ],
        "facts": [],
    }
    r = _sel(bag, why={"trigger": "glosa_medicao"})
    assert r["primary_service"]["service_id"] == "medicoes_glosas_memoria"


def test_case_c_small_growing_portfolio_gestao_or_backoffice() -> None:
    bag = {
        "contracts": [
            {
                "id": f"c{i}",
                "object": f"obra municipal expansão {i}",
                "start_date": "2025-01-01",
                "age_days": 200 + i,
                "orgao": f"Prefeitura {i}",
                "uf": "SP" if i % 2 == 0 else "MG",
                "has_reajuste": False,
            }
            for i in range(4)
        ],
        "facts": [],
        "signals": {"rapid_growth": True},
    }
    r = _sel(
        bag,
        structure={"structure_class": "lean", "lean_signals": ["thin_staff", "owner_operated"]},
        why={"trigger": ""},
    )
    assert r["primary_service"]["service_id"] in {
        "gestao_monitoramento_contratual",
        "reforco_temporario_backoffice",
    }
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"


def test_case_d_aditivos_recentes() -> None:
    bag = {
        "contracts": [
            {
                "id": "c1",
                "object": "termo aditivo de acréscimo quantitativo",
                "start_date": "2023-01-01",
                "age_days": 900,
                "has_addendum": True,
                "addendum_count": 2,
                "has_reajuste": False,
            }
        ],
        "facts": [],
    }
    r = _sel(bag, why={"trigger": "addendum"})
    assert r["primary_service"]["service_id"] in {
        "aditivos_extracontratuais",
        "reequilibrio_economico_financeiro",
    }


def test_case_e_real_anualidade_reajuste_wins_with_evidence() -> None:
    bag = {
        "contracts": [
            {
                "id": "c1",
                "object": "pavimentação asfáltica etapa única",
                "start_date": "2023-06-01",
                "age_days": 800,
                "has_reajuste": False,
                "has_addendum": False,
            }
        ],
        "facts": [{"text": "maduro sem formalização de reajuste", "epistemic_class": "confirmed"}],
    }
    r = _sel(bag, why={"trigger": "mature_no_reajuste"})
    assert r["primary_service"]["service_id"] == "estruturacao_pleito_reajuste"


def test_normalize_recent_tender_signal_feeds_router() -> None:
    """Normalize must surface recent_tender_activity so reajuste is not default."""
    raw = {
        "cnpj14": "12345678000199",
        "contracts": [
            {
                "id": "1",
                "objeto": "Contratação via edital de licitação para obras",
                "data_publicacao": "2026-07-01",
                "data_inicio": "2026-07-15",
            },
            {
                "id": "2",
                "objeto": "Pregão eletrônico serviços de engenharia",
                "data_publicacao": "2026-06-01",
                "data_inicio": "2026-06-20",
            },
        ],
    }
    bag = normalize_record(raw, as_of="2026-08-10")
    assert bag["signals"].get("recent_tender_activity") is True
    r = _sel(bag)
    assert r["primary_service"]["service_id"] != "estruturacao_pleito_reajuste"


def test_service_monoculture_flags_95pct_reajuste() -> None:
    rows = [{"service_id": "estruturacao_pleito_reajuste", "confidence": 0.5} for _ in range(40)]
    rows += [{"service_id": "gestao_monitoramento_contratual", "confidence": 0.6} for _ in range(1)]
    dist = build_service_distribution(rows)
    assert dist["SERVICE_MONOCULTURE"]["flagged"] is True
    assert dist["SERVICE_MONOCULTURE"]["causal_diagnosis_required"] is True
    assert "REAJUSTE_MONOCULTURE" in (dist["SERVICE_MONOCULTURE"]["causal_diagnosis"] or "")


def test_service_monoculture_not_flagged_on_diverse_mix() -> None:
    rows = (
        [{"service_id": "estruturacao_pleito_reajuste"} for _ in range(10)]
        + [{"service_id": "gestao_monitoramento_contratual"} for _ in range(10)]
        + [{"service_id": "apoio_licitacoes_propostas"} for _ in range(10)]
    )
    dist = build_service_distribution(rows)
    assert dist["SERVICE_MONOCULTURE"]["flagged"] is False
    mono = diagnose_service_monoculture(dist["distribution"], total=30)
    assert mono["flagged"] is False
