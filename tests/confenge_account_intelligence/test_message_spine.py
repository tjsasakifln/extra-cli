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
    assert (
        is_hollow_fact(
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
        )
        is False
    )


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
