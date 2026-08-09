"""MessageSpine: concrete contract hook only — never portfolio-count in body."""

from __future__ import annotations

from scripts.confenge_account_intelligence.message_spine import (
    build_message_spine,
    is_hollow_fact,
)
from scripts.confenge_account_intelligence.pipeline import build_dossier


def test_is_hollow_portfolio_count() -> None:
    assert is_hollow_fact("Portfólio público observado com 3 contrato(s) no input.") is True
    assert is_hollow_fact("UFs observadas nos contratos: SC, PR") is True
    # Align with COPY_CONTEXT generic markers (skeptic gap)
    assert (
        is_hollow_fact(
            "Em 2026-08-09, há portfólio público observável sem dor contratual concreta "
            "dominante — ângulo de revisão/diagnóstico focal."
        )
        is True
    )
    assert (
        is_hollow_fact(
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
        )
        is False
    )


def test_portfolio_review_why_now_not_generic_when_contract_hook() -> None:
    """MessageSpine why_now must pass evaluate_copy_context_ready (not hollow template)."""
    from scripts.confenge_contact_resolution.send_readiness import evaluate_copy_context_ready
    from scripts.confenge_account_intelligence.pipeline import build_dossier

    bag = {
        "razao_social": "SAMP CONSTRUTORA DE OBRAS LTDA",
        "cnpj14": "02810894000100",
        "contracts": [
            {
                "id": "1",
                "object": (
                    "Contratação para execução de pavimentação asfáltica de vias urbana "
                    "em CBUQ, 9.522,11 m², incluindo serviços preliminares"
                ),
                "orgao": "Diretoria de Obras",
                "uf": "PR",
                "value_brl": 5_200_000,
            }
            for _ in range(3)
        ],
    }
    d = build_dossier(bag)
    spine = d.get("message_spine") or {}
    assert is_hollow_fact(spine.get("why_now")) is False
    assert "portfólio público observável" not in (spine.get("why_now") or "").lower()
    assert spine.get("complete") is True
    company = {
        "why_this_account": d["why_this_account"],
        "why_now": spine["why_now"],
        "observed_fact": d["observed_fact"],
        "service_code": d["primary_service"]["service_id"],
        "micro_offer_code": d["micro_offer_code"],
        "evidence_ids": d.get("fact_evidence_ids") or ["e1"],
        "cta": d["cta"],
        "primary_service": d["primary_service"],
        "service_candidates": d.get("service_candidates") or [],
    }
    res = evaluate_copy_context_ready(company)
    assert res.copy_context_ready is True, res.missing_fields


def test_spine_prefers_contract_object_not_confirmed_zero() -> None:
    bag = {
        "razao_social": "ACME CONSTRUTORA LTDA",
        "contracts": [
            {
                "id": "C-9",
                "object": "Pavimentação asfáltica em CBUQ de vias urbanas no município de Coxilha",
                "orgao": "Prefeitura de Coxilha",
                "uf": "RS",
                "value_brl": 1_200_000,
            }
        ],
    }
    layers = {
        "confirmed_facts": [
            {
                "id": "cf-portfolio-count",
                "text": "Portfólio público observado com 1 contrato(s) no input.",
                "epistemic_class": "confirmed",
            }
        ]
    }
    selection = {
        "primary_service": {
            "service_id": "gestao_monitoramento_contratual",
            "approach_mode": "diagnostico_focal",
        }
    }
    spine = build_message_spine(
        bag,
        why={"trigger": "portfolio_review", "temporal_fact": "Portfólio multi-contrato ativo"},
        selection=selection,
        layers=layers,
    )
    assert spine.complete is True
    assert "portfólio público observado com" not in spine.observed_fact.lower()
    assert "pavimentação" in spine.observed_fact.lower() or "pavimentacao" in spine.observed_fact.lower()
    assert spine.body_seed_fact == spine.observed_fact
    assert spine.why_this_account
    assert "portfólio público observado com" not in spine.why_this_account.lower()


def test_dossier_observed_fact_matches_spine_not_portfolio_count(addendum_signals: dict) -> None:
    d = build_dossier(addendum_signals)
    assert d.get("observed_fact")
    assert "portfólio público observado com" not in (d["observed_fact"] or "").lower()
    assert d.get("body_seed_fact") == d.get("observed_fact")
    spine = d.get("message_spine") or {}
    assert spine.get("observed_fact") == d["observed_fact"]
    # Body seed must never be portfolio-count even if confirmed[0] is
    for item in d.get("confirmed_facts") or []:
        if item.get("id") == "cf-portfolio-count":
            assert d["observed_fact"] != item.get("text")
