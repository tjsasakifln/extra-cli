"""The 7 named red-team cases of story-outreach-claim-policy-01 (AC 12-18).

Each case is an individually named test so it traces directly back to the story.
"""

from __future__ import annotations

from datetime import date, timedelta

from scripts.confenge_account_intelligence.facts import build_epistemic_layers, why_now
from scripts.confenge_account_intelligence.message_spine import (
    _extract_temporal_event,
    build_message_spine,
    extract_contract_hook,
)
from scripts.confenge_account_intelligence.normalize import normalize_record
from scripts.confenge_claim_policy import (
    CURRENT_ACTIONABLE,
    HISTORICAL_CONTEXT,
    PAST_ONLY,
    PRESENT_CONFIRMED,
    PURPOSE_WHY_NOW,
    PURPOSE_WHY_YOU,
    RECENT_RETROSPECTIVE,
    ClaimCandidate,
    compute_copy_hash,
    evaluate_claim_policy,
    is_tense_permitted,
)

TODAY = date.today()
BIG_OBJECT = (
    "Execução de obra de pavimentação asfáltica em CBUQ, drenagem pluvial e "
    "sinalização viária em vias urbanas do município"
)
SMALL_OBJECT = "Serviços de manutenção predial corretiva e preventiva em unidades administrativas"


def _bag(contracts: list[dict[str, object]]) -> dict[str, object]:
    return normalize_record(
        {"cnpj14": "02810894000100", "razao_social": "ACME CONSTRUTORA LTDA", "contracts": contracts},
        as_of=TODAY.isoformat(),
    )


def _completed_candidate() -> ClaimCandidate:
    return ClaimCandidate(
        contract_id="C-COMPLETED",
        lifecycle_state="COMPLETED",
        evidence_ids=("cf-contract-C-COMPLETED",),
        has_hollow_fact=False,
        event_date=TODAY - timedelta(days=400),
    )


# --- Case 1 ------------------------------------------------------------------


def test_red_team_1_completed_contract_cannot_claim_em_execucao() -> None:
    """COMPLETED + copy alleging "em execução" => blocked."""
    res = evaluate_claim_policy(_completed_candidate(), evaluated_as_of=TODAY, purpose=PURPOSE_WHY_NOW)
    assert is_tense_permitted(res, PRESENT_CONFIRMED) is False
    assert res.outreach_use_class != CURRENT_ACTIONABLE
    assert res.why_now_eligible is False


# --- Case 2 ------------------------------------------------------------------


def test_red_team_2_completed_contract_may_claim_public_history_in_past_tense() -> None:
    """COMPLETED + "no histórico público vocês executaram" => allowed (past only)."""
    res = evaluate_claim_policy(_completed_candidate(), evaluated_as_of=TODAY, purpose=PURPOSE_WHY_YOU)
    assert res.allowed_tense == PAST_ONLY
    assert res.outreach_use_class in {RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT}
    assert res.why_you_eligible is True
    assert is_tense_permitted(res, PAST_ONLY) is True


# --- Case 3 ------------------------------------------------------------------


def test_red_team_3_unknown_published_yesterday_does_not_authorize_present() -> None:
    """UNKNOWN lifecycle published yesterday must not become a STRONG present claim."""
    bag = _bag(
        [
            {
                "contrato_id": "C-PUB",
                "object": BIG_OBJECT,
                "orgao": "Prefeitura de Coxilha",
                "uf": "RS",
                "value_brl": 1_200_000,
                "publication_date": (TODAY - timedelta(days=1)).isoformat(),
            }
        ]
    )
    contract = bag["contracts"][0]
    assert contract["lifecycle_state"] == "UNKNOWN"

    text, strength = _extract_temporal_event(bag, {})
    assert strength != "STRONG"
    lowered = text.lower()
    assert "evento contratual público recente" not in lowered
    assert "marco recente" not in lowered

    # facts.py path (no addendum → policy still attached to the candidate)
    layers = build_epistemic_layers(bag)
    why = why_now(bag, layers)
    # LOW-002: the old assert used a default and passed vacuously when the key was
    # absent. Both branches are now checked explicitly — absence is only tolerated for
    # the documented portfolio_review fallback, and presence must say UNKNOWN.
    if "lifecycle_state" in why:
        assert why["lifecycle_state"] == "UNKNOWN"
        assert why.get("allowed_tense") in {"NEUTRAL_FACTUAL", "PAST_ONLY"}
        assert why.get("outreach_use_class") != "CURRENT_ACTIONABLE"
    else:
        assert why["trigger"] == "portfolio_review"
        assert "outreach_use_class" not in why
    lowered_fact = str(why.get("temporal_fact", "")).lower()
    assert "em execução" not in lowered_fact
    assert "vigência ativa" not in lowered_fact


# --- Case 4 ------------------------------------------------------------------


def test_red_team_4_why_you_uses_big_history_while_why_now_only_uses_current() -> None:
    """why_you may cite the large historical contract; why_now only a valid CURRENT one."""
    bag = _bag(
        [
            {
                "contrato_id": "C-HIST",
                "object": BIG_OBJECT,
                "orgao": "DNIT",
                "uf": "SC",
                "value_brl": 48_000_000,
                "start_date": (TODAY - timedelta(days=1800)).isoformat(),
                "end_date": (TODAY - timedelta(days=900)).isoformat(),
            },
            {
                "contrato_id": "C-ATIVO",
                "object": SMALL_OBJECT,
                "orgao": "Prefeitura de Palhoça",
                "uf": "SC",
                "value_brl": 320_000,
                "start_date": (TODAY - timedelta(days=30)).isoformat(),
                "end_date": (TODAY + timedelta(days=300)).isoformat(),
            },
        ]
    )
    assert bag["contracts"][0]["lifecycle_state"] == "COMPLETED"
    assert bag["contracts"][1]["lifecycle_state"] == "ACTIVE_PROVEN"

    why_you_hook, why_you_ids = extract_contract_hook(bag, purpose=PURPOSE_WHY_YOU)
    why_now_hook, why_now_ids = extract_contract_hook(bag, purpose=PURPOSE_WHY_NOW)

    assert "cf-contract-C-HIST" in why_you_ids
    assert why_you_hook.startswith("objeto:")
    assert why_now_ids == ["cf-contract-C-ATIVO"]
    assert why_now_hook != why_you_hook


def test_red_team_4b_why_now_is_empty_when_only_history_exists() -> None:
    bag = _bag(
        [
            {
                "contrato_id": "C-HIST",
                "object": BIG_OBJECT,
                "orgao": "DNIT",
                "uf": "SC",
                "value_brl": 48_000_000,
                "start_date": (TODAY - timedelta(days=1800)).isoformat(),
                "end_date": (TODAY - timedelta(days=900)).isoformat(),
            }
        ]
    )
    assert extract_contract_hook(bag, purpose=PURPOSE_WHY_NOW) == ("", [])
    hook, ids = extract_contract_hook(bag, purpose=PURPOSE_WHY_YOU)
    assert hook and ids


# --- Case 5 ------------------------------------------------------------------


def test_red_team_5_no_eligible_why_now_invents_zero_urgency() -> None:
    """No CURRENT_ACTIONABLE candidate ⇒ no synthetic urgency text at all."""
    bag = _bag(
        [
            {
                "contrato_id": "C-OLD",
                "object": BIG_OBJECT,
                "orgao": "DNIT",
                "uf": "SC",
                "value_brl": 4_000_000,
                "start_date": (TODAY - timedelta(days=2000)).isoformat(),
                "end_date": (TODAY - timedelta(days=1200)).isoformat(),
            }
        ]
    )
    spine = build_message_spine(
        bag,
        why={"trigger": "portfolio_review"},
        selection={"primary_service": {"service_id": "gestao_monitoramento_contratual"}},
        layers={"confirmed_facts": []},
    )
    assert spine.why_now == ""
    assert spine.complete is False
    assert "why_now_weak_or_hollow" in spine.incomplete_reasons


# --- Case 6 ------------------------------------------------------------------


def test_red_team_6_addendum_of_closed_contract_is_past_never_recent_or_active() -> None:
    """The literal bug of facts.py:306 — addendum alone must not read as current."""
    bag = _bag(
        [
            {
                "contrato_id": "C-ENC",
                "object": BIG_OBJECT + " com aditivo de prazo",
                "orgao": "Prefeitura de Içara",
                "uf": "SC",
                "value_brl": 2_500_000,
                "start_date": (TODAY - timedelta(days=1400)).isoformat(),
                "end_date": (TODAY - timedelta(days=700)).isoformat(),
                "addendum_count": 2,
            }
        ]
    )
    assert bag["contracts"][0]["lifecycle_state"] == "COMPLETED"
    layers = build_epistemic_layers(bag)
    why = why_now(bag, layers)
    assert why["trigger"] == "addendum"
    text = str(why["temporal_fact"]).lower()
    assert "recente ou ativo" not in text
    assert "encerrado" in text
    assert why["allowed_tense"] == PAST_ONLY
    assert why["why_now_eligible"] is False


def test_red_team_6b_addendum_of_active_contract_may_read_as_active() -> None:
    bag = _bag(
        [
            {
                "contrato_id": "C-ATV",
                "object": BIG_OBJECT + " com aditivo de prazo",
                "orgao": "Prefeitura de Içara",
                "uf": "SC",
                "value_brl": 2_500_000,
                "start_date": (TODAY - timedelta(days=60)).isoformat(),
                "end_date": (TODAY + timedelta(days=300)).isoformat(),
                "addendum_count": 1,
            }
        ]
    )
    layers = build_epistemic_layers(bag)
    why = why_now(bag, layers)
    assert why["allowed_tense"] == PRESENT_CONFIRMED
    assert "vigência ativa comprovada" in str(why["temporal_fact"])


# --- Case 7 ------------------------------------------------------------------


def test_red_team_7_changing_the_copy_body_changes_the_copy_hash() -> None:
    candidate = _completed_candidate()
    body_a = "Olá, vimos que vocês executaram a obra X no histórico público."
    body_b = "Olá, vimos que vocês executaram a obra Y no histórico público."
    res_a = evaluate_claim_policy(candidate, evaluated_as_of=TODAY, copy_body=body_a)
    res_b = evaluate_claim_policy(candidate, evaluated_as_of=TODAY, copy_body=body_b)
    assert res_a.contract_id == res_b.contract_id
    assert res_a.evidence_ids == res_b.evidence_ids
    assert res_a.copy_hash != res_b.copy_hash
    assert res_a.copy_hash == compute_copy_hash(body_a)


def test_two_active_contracts_demote_to_historical_instead_of_killing_the_message() -> None:
    """AC 21 fail-closes the CURRENT claim, not the whole message.

    Two valid CURRENT candidates cannot both be cited, so the spine carries the
    strongest candidate demoted to a safe historical claim (neutral tense) rather
    than blocking every citation for a common multi-contract active portfolio.
    """
    from scripts.confenge_contact_resolution.send_readiness import evaluate_factual_claim_safe

    def _active(i: int, obj: str) -> dict[str, object]:
        return {
            "contrato_id": f"C-{i}",
            "object": obj,
            "orgao": f"Prefeitura {i}",
            "uf": "SC",
            "value_brl": 1_000_000 * i,
            "start_date": (TODAY - timedelta(days=30)).isoformat(),
            "end_date": (TODAY + timedelta(days=300)).isoformat(),
        }

    bag = _bag([_active(1, BIG_OBJECT), _active(2, SMALL_OBJECT)])
    assert [c["lifecycle_state"] for c in bag["contracts"]] == ["ACTIVE_PROVEN", "ACTIVE_PROVEN"]

    spine = build_message_spine(
        bag,
        why={"trigger": "portfolio_review"},
        selection={"primary_service": {"service_id": "gestao_monitoramento_contratual"}},
        layers={"confirmed_facts": []},
    )
    policy = spine.claim_policy
    assert policy["outreach_use_class"] == HISTORICAL_CONTEXT
    assert policy["allowed_tense"] != PRESENT_CONFIRMED
    assert policy["requires_current_authority"] is False
    assert "multiple_current_claims_fail_closed" in policy["reason_codes"]

    safe, _ = evaluate_factual_claim_safe({"message_spine": spine.as_dict()})
    assert safe is True
