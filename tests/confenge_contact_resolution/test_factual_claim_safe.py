"""FACTUAL_CLAIM_SAFE gate in send_readiness (story-outreach-claim-policy-01, AC 26-28)."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.confenge_claim_policy import (
    CURRENT_ACTIONABLE,
    HISTORICAL_CONTEXT,
    NEUTRAL_FACTUAL,
    PAST_ONLY,
    PRESENT_CONFIRMED,
    RECENT_RETROSPECTIVE,
)
from scripts.confenge_contact_resolution.send_readiness import (
    CopyContextResult,
    evaluate_copy_context_ready,
    evaluate_factual_claim_safe,
)

TODAY = date.today()


def _ready_company(**extra: object) -> dict[str, object]:
    company: dict[str, object] = {
        "why_this_account": ("Vocês executaram pavimentação asfáltica em CBUQ junto à Prefeitura de Coxilha (RS)."),
        "why_now": (
            "Marco contratual datado no portfólio: publicação em 2026-06-15; "
            "órgão Prefeitura de Coxilha; objeto: pavimentação asfáltica em CBUQ."
        ),
        "observed_fact": (
            "objeto: Execução de pavimentação asfáltica em CBUQ de vias urbanas; órgão: Prefeitura de Coxilha; UF RS"
        ),
        "service_code": "gestao_monitoramento_contratual",
        "micro_offer_code": "PUBLIC_DATA_SNAPSHOT",
        "evidence_ids": ["cf-contract-C-1"],
        "cta": "Faz sentido eu enviar um snapshot dos seus contratos públicos?",
    }
    company.update(extra)
    return company


def _policy(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "outreach_use_class": HISTORICAL_CONTEXT,
        "allowed_tense": PAST_ONLY,
        "claim_mode": "HISTORICAL_CONTRACT",
        "why_now_eligible": False,
        "requires_current_authority": False,
    }
    base.update(overrides)
    return base


def test_default_result_is_claim_safe_so_the_gate_can_only_subtract() -> None:
    assert CopyContextResult(copy_context_ready=True).factual_claim_safe is True


def test_absent_claim_policy_leaves_behaviour_unchanged() -> None:
    safe, reasons = evaluate_factual_claim_safe(_ready_company())
    assert safe is True
    assert reasons == []


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        pytest.param(_policy(), True, id="historical_context_past_only_is_safe"),
        pytest.param(
            _policy(outreach_use_class=RECENT_RETROSPECTIVE, allowed_tense=NEUTRAL_FACTUAL),
            True,
            id="recent_retrospective_neutral_is_safe",
        ),
        pytest.param(
            _policy(
                outreach_use_class=CURRENT_ACTIONABLE,
                allowed_tense=PRESENT_CONFIRMED,
                requires_current_authority=True,
                why_now_eligible=True,
            ),
            True,
            id="current_with_contemporary_authority_is_safe",
        ),
        pytest.param(
            _policy(
                outreach_use_class=CURRENT_ACTIONABLE,
                allowed_tense=PRESENT_CONFIRMED,
                requires_current_authority=True,
                why_now_eligible=False,
            ),
            False,
            id="current_without_contemporary_authority_is_unsafe",
        ),
        pytest.param(
            _policy(outreach_use_class="DO_NOT_CITE", allowed_tense="NONE"),
            False,
            id="do_not_cite_is_unsafe",
        ),
    ],
)
def test_factual_claim_safe_verdicts(policy: dict[str, object], expected: bool) -> None:
    safe, _ = evaluate_factual_claim_safe({"claim_policy": policy})
    assert safe is expected


def test_multiple_current_claims_fail_closed_is_unsafe() -> None:
    safe, reasons = evaluate_factual_claim_safe(
        {"claim_policy": {"claims_blocked": True, "reason_codes": ["multiple_current_claims_fail_closed"]}}
    )
    assert safe is False
    assert "multiple_current_claims_fail_closed" in reasons


def test_ac26_demotion_happens_before_the_frozen_result_is_built() -> None:
    unsafe_policy = _policy(
        outreach_use_class=CURRENT_ACTIONABLE,
        allowed_tense=PRESENT_CONFIRMED,
        requires_current_authority=True,
        why_now_eligible=False,
    )
    res = evaluate_copy_context_ready(_ready_company(claim_policy=unsafe_policy))
    assert res.factual_claim_safe is False
    assert "factual_claim_safe" in res.missing_fields
    assert res.copy_context_ready is False
    # frozen dataclass — the verdict cannot have been patched after construction
    with pytest.raises(Exception):
        res.factual_claim_safe = True  # type: ignore[misc]


def test_ac27_monotonicity_the_gate_never_promotes_a_case() -> None:
    """No case that was not copy-context-ready becomes ready because of this gate."""
    incomplete = _ready_company()
    incomplete.pop("cta")
    before = evaluate_copy_context_ready(dict(incomplete))
    after = evaluate_copy_context_ready(
        dict(incomplete, claim_policy=_policy(outreach_use_class=CURRENT_ACTIONABLE, allowed_tense=PRESENT_CONFIRMED))
    )
    assert before.copy_context_ready is False
    assert after.copy_context_ready is False
    assert set(before.missing_fields) <= set(after.missing_fields)


def test_ac28_already_safe_history_stays_eligible() -> None:
    before = evaluate_copy_context_ready(_ready_company())
    after = evaluate_copy_context_ready(_ready_company(claim_policy=_policy()))
    assert before.copy_context_ready is True
    assert after.copy_context_ready is True
    assert after.factual_claim_safe is True


def test_spine_claim_policy_is_read_from_message_spine_payload() -> None:
    company = _ready_company()
    company["message_spine"] = {"claim_policy": _policy(outreach_use_class="DO_NOT_CITE", allowed_tense="NONE")}
    safe, _ = evaluate_factual_claim_safe(company)
    assert safe is False
