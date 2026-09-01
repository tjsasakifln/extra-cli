"""AC 6, 7 and AC 20's enforcement clause — deterministic rewrite."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.confenge_claim_safety.claim_surface import CLAIM_NONE, CLAIM_PRESENT, detect_temporal_claim
from scripts.confenge_claim_safety.classify import classify_lead, link_contract
from scripts.confenge_claim_safety.policy import (
    NEEDS_RESEARCH,
    PUBLISHABLE_CLASSES,
    SAFE_HISTORICAL,
    SAFE_NO_CURRENT_CLAIM,
    UNSAFE_PRESENT_CLAIM,
)
from scripts.confenge_claim_safety.rewrite import (
    REWRITE_RULE_NEUTRALIZED,
    REWRITE_RULE_PAST_FRAME,
    rewrite_lead,
    rewrite_text,
)
from tests.confenge_claim_safety.conftest import ADDENDUM_UNSAFE_TEXT, contract, lead

TODAY = date(2026, 9, 1)
OBJETO = "Acréscimo no valor e no prazo dos serviços de reforma em salas do prédio sede do TCMRio."


def _unsafe_lead(end_date: str | None) -> dict:
    return lead(
        cnpj14="03518914000137",
        why_now_code="ADDENDUM",
        why_now=ADDENDUM_UNSAFE_TEXT,
        contracts=[contract(contract_id="c-1", objeto=OBJETO, end_date=end_date)],
    )


def _rewrite(payload: dict) -> dict:
    result = classify_lead(payload, today=TODAY)
    updated, _changed = rewrite_lead(
        payload, contract=link_contract(payload), today=TODAY, reason_codes=result.reason_codes
    )
    return updated


# --- AC 6 ------------------------------------------------------------------- #
def test_ac6_past_end_date_becomes_an_explicit_dated_historical_frame() -> None:
    payload = _unsafe_lead("2026-06-15")
    assert classify_lead(payload, today=TODAY).safety_class == UNSAFE_PRESENT_CLAIM
    updated = _rewrite(payload)
    assert updated["messaging_context"]["why_now"] == (
        "Aditivos/alterações observados em contrato público. Vigência encerrada em 15/06/2026."
    )
    assert updated["claim_safety"]["rewrite_rule"] == REWRITE_RULE_PAST_FRAME
    assert classify_lead(updated, today=TODAY).safety_class == SAFE_HISTORICAL


# --- AC 7 ------------------------------------------------------------------- #
@pytest.mark.parametrize("end_date", ["2027-01-21", None])
def test_ac7_future_or_null_end_date_drops_the_temporal_assertion(end_date: str | None) -> None:
    payload = _unsafe_lead(end_date)
    assert classify_lead(payload, today=TODAY).safety_class == UNSAFE_PRESENT_CLAIM
    updated = _rewrite(payload)
    text = updated["messaging_context"]["why_now"]
    assert text == "Aditivos/alterações observados em contrato público."
    # The observed fact survives; only the assertion of currency is gone.
    assert "Aditivos/alterações observados" in text
    assert updated["claim_safety"]["rewrite_rule"] == REWRITE_RULE_NEUTRALIZED
    assert classify_lead(updated, today=TODAY).safety_class == SAFE_NO_CURRENT_CLAIM


def test_rewrite_updates_every_assertion_field_not_just_why_now() -> None:
    """``moment.summary`` mirrors ``why_now``; leaving it behind reships the claim."""
    payload = _unsafe_lead("2026-06-15")
    assert payload["moment"]["summary"] == ADDENDUM_UNSAFE_TEXT
    updated = _rewrite(payload)
    assert updated["moment"]["summary"] == updated["messaging_context"]["why_now"]
    assert detect_temporal_claim(updated["moment"]["summary"]) != CLAIM_PRESENT


def test_rewrite_does_not_mutate_the_caller_payload() -> None:
    payload = _unsafe_lead("2026-06-15")
    _rewrite(payload)
    assert payload["messaging_context"]["why_now"] == ADDENDUM_UNSAFE_TEXT
    assert payload["moment"]["summary"] == ADDENDUM_UNSAFE_TEXT


# --- AC 20 enforcement ------------------------------------------------------ #
@pytest.mark.parametrize("code", ["MATURE_NO_REAJUSTE", "A_SEVENTH_TRIGGER_NOBODY_DECLARED"])
def test_ac20_needs_research_leads_are_rewritten_into_a_publishable_class(code: str) -> None:
    payload = lead(
        cnpj14="03518914000137",
        why_now_code=code,
        why_now="Contrato público vigente com obras em execução, sem prova de reajuste no input.",
        contracts=[contract(contract_id="c-1", objeto=OBJETO, end_date="2027-01-21")],
    )
    assert classify_lead(payload, today=TODAY).safety_class == NEEDS_RESEARCH
    updated = _rewrite(payload)
    assert detect_temporal_claim(updated["messaging_context"]["why_now"]) == CLAIM_NONE
    post = classify_lead(updated, today=TODAY)
    assert post.safety_class == SAFE_NO_CURRENT_CLAIM
    assert post.safety_class in PUBLISHABLE_CLASSES


# --- neutralizer shapes ----------------------------------------------------- #
@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (
            "Aditivos/alterações observados em contrato público recente ou ativo.",
            "Aditivos/alterações observados em contrato público.",
        ),
        # Shape introduced by the concurrent CLAIM_POLICY refactor of facts.py:
        # a prepositional phrase must be removed whole, not token by token, or
        # the copy degrades into "em contrato público com comprovada".
        (
            "Aditivos/alterações observados em contrato público com vigência ativa comprovada.",
            "Aditivos/alterações observados em contrato público.",
        ),
        (
            "Aditivos/alterações observados em registro contratual público, sem vigência atual comprovada no input.",
            "Aditivos/alterações observados em registro contratual público, sem vigência atual comprovada no input.",
        ),
    ],
)
def test_neutralizer_produces_well_formed_copy(original: str, expected: str) -> None:
    assert rewrite_text(original, past_frame=None) == expected


def test_neutralizer_never_returns_an_empty_why_now() -> None:
    neutral = rewrite_text("Vigente.", past_frame=None)
    assert neutral.strip()
    assert detect_temporal_claim(neutral) == CLAIM_NONE
