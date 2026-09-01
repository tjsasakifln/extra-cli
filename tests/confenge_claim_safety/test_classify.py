"""AC 1-5, 16, 20 — the five classes across every activity state.

Pure classification: no I/O, synthetic contract + ``why_now_code`` fixtures.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.confenge_claim_safety.classify import (
    AMBIGUOUS_WHY_NOW_CODES,
    RECOGNIZED_WHY_NOW_CODES,
    active_proven_reason_codes,
    class_distribution,
    classify_lead,
    link_contract,
)
from scripts.confenge_claim_safety.policy import (
    CLAIM_SAFETY_CLASSES,
    NEEDS_RESEARCH,
    PUBLISHABLE_CLASSES,
    REASON_ACTIVE_PROVEN_UNREACHABLE,
    REASON_AMBIGUOUS_TEMPLATE,
    REASON_NO_LINKED_CONTRACT,
    REASON_UNRECOGNIZED_TEMPLATE,
    SAFE_CURRENT_PROVEN,
    SAFE_HISTORICAL,
    SAFE_NO_CURRENT_CLAIM,
    UNSAFE_PRESENT_CLAIM,
)
from scripts.contracts_truth import (
    ACTIVE_PROVEN,
    ACTIVITY_STATES,
    CANCELLED,
    COMPLETED,
    SUSPENDED,
    TERMINATED,
    UNKNOWN,
)
from tests.confenge_claim_safety.conftest import ADDENDUM_UNSAFE_TEXT, PORTFOLIO_REVIEW_TEXT, contract, lead

TODAY = date(2026, 9, 1)

OBJETO = (
    "Acréscimo no valor e no prazo dos serviços de reforma em salas do prédio sede do "
    "Tribunal de Contas do Município do Rio de Janeiro - TCMRio, sob regime de Empreitada."
)

# Status tokens that ``contracts_truth`` maps to each non-ACTIVE_PROVEN state.
# Imported states, never redefined: the mapping below only chooses an input.
_STATUS_FOR_STATE = {
    COMPLETED: "encerrado",
    CANCELLED: "cancelado",
    TERMINATED: "rescindido",
    SUSPENDED: "suspenso",
    UNKNOWN: None,
}


def _addendum_lead(**contract_kwargs: object) -> dict:
    return lead(
        cnpj14="03518914000137",
        why_now_code="ADDENDUM",
        why_now=ADDENDUM_UNSAFE_TEXT,
        contracts=[contract(contract_id="c-1", objeto=OBJETO, **contract_kwargs)],  # type: ignore[arg-type]
    )


# --- AC 1 ------------------------------------------------------------------- #
@pytest.mark.parametrize("code", ["PORTFOLIO_REVIEW", "INSUFFICIENT_FACTS"])
def test_ac1_templates_without_a_claim_are_safe(code: str) -> None:
    payload = lead(
        cnpj14="12345678000195",
        why_now_code=code,
        why_now=PORTFOLIO_REVIEW_TEXT.format(objeto=OBJETO[:140], orgao="TCMRio", uf="RJ"),
        contracts=[contract(contract_id="c-2", objeto=OBJETO, end_date="2027-01-21")],
    )
    assert classify_lead(payload, today=TODAY).safety_class == SAFE_NO_CURRENT_CLAIM


# --- AC 2 ------------------------------------------------------------------- #
def test_ac2_present_claim_over_active_proven_is_safe_current_proven() -> None:
    payload = _addendum_lead(status="ativo", start_date="2026-01-01", end_date="2027-01-01")
    result = classify_lead(payload, today=TODAY)
    assert result.activity_state == ACTIVE_PROVEN
    assert result.safety_class == SAFE_CURRENT_PROVEN


def test_ac2_zero_safe_current_proven_is_reported_with_an_explicit_reason_code() -> None:
    """A structurally empty class is reported as 0 with a reason, never hidden."""
    results = [classify_lead(_addendum_lead(end_date="2027-01-21"), today=TODAY)]
    distribution = class_distribution(results)
    assert distribution[SAFE_CURRENT_PROVEN] == 0
    assert set(distribution) == set(CLAIM_SAFETY_CLASSES)
    assert active_proven_reason_codes(results) == [REASON_ACTIVE_PROVEN_UNREACHABLE]


def test_ac2_published_payload_shape_cannot_reach_active_proven() -> None:
    """100% of published contracts carry ``start_date: null`` — no vigência window."""
    payload = _addendum_lead(start_date=None, end_date="2027-01-21")
    assert classify_lead(payload, today=TODAY).activity_state == UNKNOWN


# --- AC 3 ------------------------------------------------------------------- #
def test_ac3_explicit_past_frame_anchored_on_a_date_is_safe_historical() -> None:
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="ADDENDUM",
        why_now="Aditivos/alterações observados em contrato público. Vigência encerrada em 15/06/2026.",
        contracts=[contract(contract_id="c-1", objeto=OBJETO, end_date="2026-06-15")],
    )
    assert classify_lead(payload, today=TODAY).safety_class == SAFE_HISTORICAL


# --- AC 4 + AC 16 ----------------------------------------------------------- #
@pytest.mark.parametrize("state", sorted(ACTIVITY_STATES - {ACTIVE_PROVEN}))
def test_ac4_ac16_present_claim_over_any_unproven_state_is_unsafe(state: str) -> None:
    token = _STATUS_FOR_STATE[state]
    if state == UNKNOWN:
        # UNKNOWN is what the published payload actually produces: no status token
        # and no closed vigência window (start_date is NULL for 100% of contracts).
        payload = _addendum_lead(start_date=None, end_date="2027-01-01")
    else:
        payload = _addendum_lead(status=token, start_date="2026-01-01", end_date="2027-01-01")
    result = classify_lead(payload, today=TODAY)
    assert result.activity_state == state, f"fixture did not reach {state}"
    assert result.safety_class == UNSAFE_PRESENT_CLAIM


def test_ac4_unknown_activity_is_never_promoted_to_safe() -> None:
    result = classify_lead(_addendum_lead(end_date=None), today=TODAY)
    assert result.activity_state == UNKNOWN
    assert result.safety_class == UNSAFE_PRESENT_CLAIM
    assert result.safety_class not in PUBLISHABLE_CLASSES


# --- AC 5 ------------------------------------------------------------------- #
def test_ac5_present_claim_without_any_contract_needs_research() -> None:
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="ADDENDUM",
        why_now=ADDENDUM_UNSAFE_TEXT,
        contracts=[],
        fact_to_mention="",
    )
    result = classify_lead(payload, today=TODAY)
    assert result.safety_class == NEEDS_RESEARCH
    assert REASON_NO_LINKED_CONTRACT in result.reason_codes


def test_ac5_ambiguous_multi_contract_binding_fails_closed() -> None:
    """No ``objeto:`` quote and several contracts: never bind to ``contracts[0]``."""
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="ADDENDUM",
        why_now=ADDENDUM_UNSAFE_TEXT,
        contracts=[
            contract(contract_id="c-1", objeto=OBJETO, end_date="2026-06-15"),
            contract(contract_id="c-2", objeto="Outro objeto totalmente distinto do primeiro.", end_date=None),
        ],
        fact_to_mention="órgão: TCMRio; UF RJ",
    )
    assert link_contract(payload) is None
    result = classify_lead(payload, today=TODAY)
    assert result.safety_class == NEEDS_RESEARCH
    assert REASON_NO_LINKED_CONTRACT in result.reason_codes


def test_link_contract_picks_the_quoted_object_not_the_first_one() -> None:
    quoted = contract(contract_id="c-quoted", objeto=OBJETO, end_date="2026-06-15")
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="ADDENDUM",
        why_now=ADDENDUM_UNSAFE_TEXT,
        contracts=[contract(contract_id="c-other", objeto="Objeto diferente e mais longo.", end_date=None), quoted],
        fact_to_mention=f"objeto: {OBJETO[:140]}; órgão: TCMRio; UF RJ; R$ 38,959",
    )
    linked = link_contract(payload)
    assert linked is not None and linked["id"] == "c-quoted"


# --- AC 20 ------------------------------------------------------------------ #
def test_ac20_unrecognized_why_now_code_is_needs_research_never_safe() -> None:
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="A_SEVENTH_TRIGGER_NOBODY_DECLARED",
        why_now="Contrato público em execução neste momento.",
        contracts=[contract(contract_id="c-1", objeto=OBJETO, end_date="2027-01-21")],
    )
    result = classify_lead(payload, today=TODAY)
    assert result.safety_class == NEEDS_RESEARCH
    assert result.reason_codes == (REASON_UNRECOGNIZED_TEMPLATE,)
    assert result.safety_class not in PUBLISHABLE_CLASSES


def test_ac20_unrecognized_code_is_needs_research_even_when_its_text_is_harmless() -> None:
    """Fail-closed is about the template we cannot read, not about the words."""
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="SOME_FUTURE_TRIGGER",
        why_now="Texto absolutamente neutro sem qualquer afirmação temporal.",
        contracts=[contract(contract_id="c-1", objeto=OBJETO, end_date="2027-01-21")],
    )
    assert classify_lead(payload, today=TODAY).safety_class == NEEDS_RESEARCH


def test_ac20_mature_no_reajuste_is_needs_research_by_explicit_decision() -> None:
    assert "MATURE_NO_REAJUSTE" in RECOGNIZED_WHY_NOW_CODES
    assert "MATURE_NO_REAJUSTE" in AMBIGUOUS_WHY_NOW_CODES
    payload = lead(
        cnpj14="03518914000137",
        why_now_code="MATURE_NO_REAJUSTE",
        why_now=(
            "Contrato maduro (com data de início observada) sem prova de reajuste no input "
            "— janela potencial de reajuste."
        ),
        contracts=[contract(contract_id="c-1", objeto=OBJETO, start_date="2024-01-01", end_date="2027-01-21")],
    )
    result = classify_lead(payload, today=TODAY)
    assert result.safety_class == NEEDS_RESEARCH
    assert REASON_AMBIGUOUS_TEMPLATE in result.reason_codes


def test_needs_research_is_not_publishable() -> None:
    assert NEEDS_RESEARCH not in PUBLISHABLE_CLASSES
    assert UNSAFE_PRESENT_CLAIM not in PUBLISHABLE_CLASSES
