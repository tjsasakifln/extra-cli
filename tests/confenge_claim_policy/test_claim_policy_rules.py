"""Business rules of CLAIM_POLICY (story-outreach-claim-policy-01, AC 1-11, 19-23a, 31-33)."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.confenge_claim_policy import (
    CLAIM_MODE_NONE,
    CURRENT_ACTIONABLE,
    CURRENT_CONTRACT,
    DO_NOT_CITE,
    HISTORICAL_CONTEXT,
    HISTORICAL_CONTRACT,
    NEUTRAL_FACTUAL,
    PAST_ONLY,
    PRESENT_CONFIRMED,
    PURPOSE_WHY_NOW,
    PURPOSE_WHY_YOU,
    RAW_STATUS_FALLBACK_STATES,
    REASON_RAW_STATUS_NOT_PROMOTABLE,
    RECENT_RETROSPECTIVE,
    TENSE_NONE,
    ClaimCandidate,
    allows_present_tense,
    compute_copy_hash,
    evaluate_claim_policy,
    is_tense_permitted,
    resolve_lifecycle_state,
    select_message_claims,
)
from scripts.confenge_claim_policy.policy import REASON_STAMPED_STATE
from scripts.contracts_truth import ACTIVE_PROVEN, ACTIVITY_STATES

AS_OF = date(2026, 9, 1)


def _candidate(**kwargs: object) -> ClaimCandidate:
    base: dict[str, object] = {
        "contract_id": "C-1",
        "evidence_ids": ("cf-contract-C-1",),
        "has_hollow_fact": False,
    }
    base.update(kwargs)
    return ClaimCandidate(**base)  # type: ignore[arg-type]


# --- Rule 1 / Rule 8 ---------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        pytest.param("COMPLETED", id="completed_history_feeds_why_you"),
        pytest.param("TERMINATED", id="terminated_history_feeds_why_you"),
    ],
)
def test_rule1_history_is_why_you_without_requiring_why_now(state: str) -> None:
    res = evaluate_claim_policy(_candidate(lifecycle_state=state), evaluated_as_of=AS_OF, purpose=PURPOSE_WHY_YOU)
    assert res.why_you_eligible is True
    assert res.why_now_eligible is False
    assert res.claim_mode == HISTORICAL_CONTRACT


def test_rule8_missing_lifecycle_degrades_to_unknown_and_never_raises() -> None:
    res = evaluate_claim_policy(_candidate(lifecycle_state=""), evaluated_as_of=AS_OF)
    assert res.lifecycle_state == "UNKNOWN"
    assert "lifecycle_absent_degraded_to_unknown" in res.reason_codes
    assert res.why_you_eligible is True
    assert res.outreach_use_class != CURRENT_ACTIONABLE


# --- Rule 2 / Rule 11 --------------------------------------------------------


def test_rule2_active_proven_alone_is_not_why_now_eligible() -> None:
    res = evaluate_claim_policy(
        _candidate(lifecycle_state="ACTIVE_PROVEN", has_contemporary_event=False),
        evaluated_as_of=AS_OF,
        purpose=PURPOSE_WHY_NOW,
    )
    assert res.outreach_use_class == CURRENT_ACTIONABLE
    assert res.why_now_eligible is False
    assert res.requires_current_authority is True  # AC 11


def test_rule2_active_proven_with_contemporary_event_is_why_now_eligible() -> None:
    res = evaluate_claim_policy(
        _candidate(
            lifecycle_state="ACTIVE_PROVEN",
            has_contemporary_event=True,
            event_date=date(2026, 8, 1),
        ),
        evaluated_as_of=AS_OF,
        purpose=PURPOSE_WHY_NOW,
    )
    assert res.outreach_use_class == CURRENT_ACTIONABLE
    assert res.claim_mode == CURRENT_CONTRACT
    assert res.why_now_eligible is True
    assert allows_present_tense(res) is True


# --- Rule 3 / Rule 7 precedence ---------------------------------------------


def test_rule3_completed_with_proof_is_retrospective_never_present() -> None:
    res = evaluate_claim_policy(
        _candidate(lifecycle_state="COMPLETED", event_date=date(2026, 6, 1)),
        evaluated_as_of=AS_OF,
    )
    assert res.outreach_use_class in {RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT}
    assert res.allowed_tense != PRESENT_CONFIRMED
    assert allows_present_tense(res) is False


def test_rule7_beats_rule3_completed_without_evidence_is_do_not_cite() -> None:
    res = evaluate_claim_policy(
        _candidate(lifecycle_state="COMPLETED", evidence_ids=()),
        evaluated_as_of=AS_OF,
    )
    assert res.outreach_use_class == DO_NOT_CITE
    assert res.allowed_tense == TENSE_NONE
    assert res.claim_mode == CLAIM_MODE_NONE
    assert "factual_hard_gate_failed" in res.reason_codes


def test_rule7_hard_gate_beats_favourable_lifecycle() -> None:
    res = evaluate_claim_policy(
        _candidate(lifecycle_state="ACTIVE_PROVEN", has_contemporary_event=True, has_hollow_fact=True),
        evaluated_as_of=AS_OF,
    )
    assert res.outreach_use_class == DO_NOT_CITE
    assert res.requires_current_authority is False
    assert "hollow_fact" in res.reason_codes


# --- Rule 4 / Rule 5 / Rule 6 / AC 32 ---------------------------------------


def test_rule4_unknown_with_recent_publication_never_authorizes_present() -> None:
    res = evaluate_claim_policy(
        _candidate(lifecycle_state="UNKNOWN", event_date=date(2026, 8, 31), has_contemporary_event=True),
        evaluated_as_of=AS_OF,
    )
    assert res.outreach_use_class != CURRENT_ACTIONABLE
    assert res.allowed_tense == NEUTRAL_FACTUAL
    assert res.why_now_eligible is False


def test_rule5_terminated_without_evidence_stays_do_not_cite() -> None:
    res = evaluate_claim_policy(_candidate(lifecycle_state="TERMINATED", evidence_ids=()), evaluated_as_of=AS_OF)
    assert res.outreach_use_class == DO_NOT_CITE


def test_rule5_terminated_with_evidence_allows_past_only() -> None:
    res = evaluate_claim_policy(_candidate(lifecycle_state="CANCELLED"), evaluated_as_of=AS_OF)
    assert res.allowed_tense == PAST_ONLY
    assert res.why_you_eligible is True


def test_ac32_suspended_is_never_current_and_never_present() -> None:
    res = evaluate_claim_policy(_candidate(lifecycle_state="SUSPENDED"), evaluated_as_of=AS_OF)
    assert res.outreach_use_class != CURRENT_ACTIONABLE
    assert res.allowed_tense != PRESENT_CONFIRMED
    assert res.why_you_eligible is True


# --- AC 21 / AC 22 selection -------------------------------------------------


def test_ac21_two_current_claims_fail_closed_with_empty_list_and_reasons() -> None:
    a = evaluate_claim_policy(
        _candidate(
            contract_id="A", evidence_ids=("e-a",), lifecycle_state="ACTIVE_PROVEN", has_contemporary_event=True
        ),
        evaluated_as_of=AS_OF,
    )
    b = evaluate_claim_policy(
        _candidate(
            contract_id="B", evidence_ids=("e-b",), lifecycle_state="ACTIVE_PROVEN", has_contemporary_event=True
        ),
        evaluated_as_of=AS_OF,
    )
    sel = select_message_claims([a, b])
    assert sel.claims == ()
    assert "multiple_current_claims_fail_closed" in sel.reason_codes


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        pytest.param(["COMPLETED", "COMPLETED"], 2, id="zero_current_all_historical_pass"),
        pytest.param(["ACTIVE_PROVEN", "COMPLETED"], 2, id="single_current_plus_history_pass"),
    ],
)
def test_ac22_zero_or_one_current_is_not_a_false_positive(states: list[str], expected: int) -> None:
    results = [
        evaluate_claim_policy(
            _candidate(
                contract_id=f"C-{i}",
                evidence_ids=(f"e-{i}",),
                lifecycle_state=s,
                has_contemporary_event=True,
            ),
            evaluated_as_of=AS_OF,
        )
        for i, s in enumerate(states)
    ]
    sel = select_message_claims(results)
    assert len(sel.claims) == expected


def test_selection_returns_empty_when_nothing_is_citable() -> None:
    blocked = evaluate_claim_policy(_candidate(evidence_ids=()), evaluated_as_of=AS_OF)
    sel = select_message_claims([blocked])
    assert sel.claims == ()
    assert "no_citable_candidate" in sel.reason_codes


# --- AC 31 / 33 vocabulary and purity ---------------------------------------


def test_ac31_no_second_lifecycle_vocabulary_is_introduced() -> None:
    states = set()
    for s in sorted(ACTIVITY_STATES) + ["", "not-a-state"]:
        states.add(evaluate_claim_policy(_candidate(lifecycle_state=s), evaluated_as_of=AS_OF).lifecycle_state)
    assert states <= set(ACTIVITY_STATES)


def test_ac33_evaluation_never_reads_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import contracts_truth

    class _NoClockDate(date):
        @classmethod
        def today(cls) -> date:  # pragma: no cover - must never be reached
            raise AssertionError("wall clock read inside CLAIM_POLICY evaluation")

    monkeypatch.setattr(contracts_truth, "date", _NoClockDate)

    res = evaluate_claim_policy(_candidate(lifecycle_state="COMPLETED"), evaluated_as_of=AS_OF)
    assert res.evaluated_as_of == AS_OF
    lifecycle = resolve_lifecycle_state(evaluated_as_of=AS_OF, start_date="2020-01-01", end_date="2021-01-01")
    assert lifecycle.state == "COMPLETED"


def test_a1_evaluated_as_of_must_be_a_real_date_not_a_string() -> None:
    with pytest.raises(TypeError):
        evaluate_claim_policy(_candidate(), evaluated_as_of="2026-09-01")  # type: ignore[arg-type]


def test_ac24_lifecycle_derivation_matches_contracts_truth_table() -> None:
    # end_date in the past WITH start_date -> COMPLETED (vigencia_ended)
    assert (
        resolve_lifecycle_state(evaluated_as_of=AS_OF, start_date="2024-01-01", end_date="2025-01-01").state
        == "COMPLETED"
    )
    # end_date in the past WITHOUT start_date -> UNKNOWN (missing_status_and_vigencia)
    assert resolve_lifecycle_state(evaluated_as_of=AS_OF, end_date="2025-01-01").state == "UNKNOWN"
    # window spanning as_of -> ACTIVE_PROVEN
    assert (
        resolve_lifecycle_state(evaluated_as_of=AS_OF, start_date="2026-01-01", end_date="2027-01-01").state
        == "ACTIVE_PROVEN"
    )
    # inverted vigência -> UNKNOWN
    assert (
        resolve_lifecycle_state(evaluated_as_of=AS_OF, start_date="2027-01-01", end_date="2026-01-01").state
        == "UNKNOWN"
    )
    # only a recent publication/start -> UNKNOWN
    assert resolve_lifecycle_state(evaluated_as_of=AS_OF, start_date="2026-08-31").state == "UNKNOWN"


def test_a4_stamped_state_takes_the_validated_path_and_never_degrades() -> None:
    """ACTIVE_PROVEN as an explicit stamped state must not silently degrade to UNKNOWN."""
    assert resolve_lifecycle_state(evaluated_as_of=AS_OF, stamped_state="ACTIVE_PROVEN").state == "ACTIVE_PROVEN"
    # A genuine PT-BR raw token still goes through classify_contract_activity.
    assert resolve_lifecycle_state(evaluated_as_of=AS_OF, raw_status="rescindido").state == "TERMINATED"


# --- MED-001 regression: raw_status may never promote ------------------------


def test_med001_raw_status_spelling_active_proven_never_promotes() -> None:
    """A textual raw_status can never reach ACTIVE_PROVEN without dated evidence.

    Regression guard for MED-001: the raw_status fallback used to route straight into
    the stamped-state path, so ``situacao='active_proven'`` with zero dates bypassed
    ``classify_contract_activity`` entirely and unlocked PRESENT_CONFIRMED.
    """
    for spelling in ("ACTIVE_PROVEN", "active_proven", "  Active_Proven  "):
        res = resolve_lifecycle_state(evaluated_as_of=AS_OF, raw_status=spelling)
        assert res.state == "UNKNOWN", spelling
        assert REASON_RAW_STATUS_NOT_PROMOTABLE in res.reasons
        assert REASON_STAMPED_STATE not in res.reasons

    # Safe-by-nature state names remain adoptable through the same fallback.
    assert ACTIVE_PROVEN not in RAW_STATUS_FALLBACK_STATES
    assert RAW_STATUS_FALLBACK_STATES == frozenset(ACTIVITY_STATES) - {ACTIVE_PROVEN}
    for safe in sorted(RAW_STATUS_FALLBACK_STATES):
        assert resolve_lifecycle_state(evaluated_as_of=AS_OF, raw_status=safe).state == safe

    # The explicit stamped path is unaffected (A4 keeps it as the trusted channel).
    assert resolve_lifecycle_state(evaluated_as_of=AS_OF, stamped_state="ACTIVE_PROVEN").state == "ACTIVE_PROVEN"

    # Dated evidence still promotes legitimately, even alongside the refused token.
    dated = resolve_lifecycle_state(
        evaluated_as_of=AS_OF,
        raw_status="ACTIVE_PROVEN",
        start_date="2026-01-01",
        end_date="2027-01-01",
    )
    assert dated.state == "ACTIVE_PROVEN"


def test_med001_normalize_record_probe_cannot_reach_present_confirmed() -> None:
    """End-to-end reproduction of the QA probe: situacao='active_proven', zero dates.

    Goes through the real ``normalize_record`` → ``why_now`` path (an addendum fires the
    pain-check that attaches the policy verdict). Before the MED-001 fix this exact bag
    produced ``lifecycle_state=ACTIVE_PROVEN`` (reason ``stamped_lifecycle_state``) and
    ``allowed_tense=PRESENT_CONFIRMED`` with the text "…vigência ativa comprovada.".
    """
    from scripts.confenge_account_intelligence.facts import build_epistemic_layers, why_now
    from scripts.confenge_account_intelligence.normalize import normalize_record

    record = normalize_record(
        {
            "cnpj14": "00000000000191",
            "razao_social": "EMPRESA PROBE LTDA",
            "contracts": [
                {
                    "id": "C-PROBE",
                    "objeto": "Execução de obra de pavimentação urbana com drenagem completa",
                    "orgao": "Prefeitura de Coxilha",
                    "uf": "RS",
                    "value_brl": 1_200_000,
                    "situacao": "active_proven",
                    "has_addendum": True,
                    "addendum_count": 2,
                }
            ],
        },
        as_of=AS_OF.isoformat(),
    )
    contract = record["contracts"][0]
    assert contract["raw_status"] == "active_proven"
    assert contract["lifecycle_state"] == "UNKNOWN"
    # Proves the refusal path actually executed inside normalize.py — the state did not
    # land on UNKNOWN for some unrelated reason.
    assert REASON_RAW_STATUS_NOT_PROMOTABLE in contract["lifecycle_reasons"]
    assert REASON_STAMPED_STATE not in contract["lifecycle_reasons"]

    why = why_now(record, build_epistemic_layers(record))
    assert why["lifecycle_state"] == "UNKNOWN"
    assert why["outreach_use_class"] != CURRENT_ACTIONABLE
    assert why["allowed_tense"] != PRESENT_CONFIRMED
    assert why["why_now_eligible"] is False
    assert "vigência ativa comprovada" not in str(why["temporal_fact"]).lower()

    verdict = evaluate_claim_policy(
        _candidate(contract_id="C-PROBE", lifecycle_state=contract["lifecycle_state"]),
        evaluated_as_of=AS_OF,
    )
    assert verdict.allowed_tense != PRESENT_CONFIRMED
    assert verdict.outreach_use_class != CURRENT_ACTIONABLE
    assert allows_present_tense(verdict) is False


def test_is_tense_permitted_refuses_present_for_history() -> None:
    hist = evaluate_claim_policy(_candidate(lifecycle_state="COMPLETED"), evaluated_as_of=AS_OF)
    assert is_tense_permitted(hist, PRESENT_CONFIRMED) is False
    assert is_tense_permitted(hist, PAST_ONLY) is True


def test_copy_hash_contract_is_pinned_sha256_utf8() -> None:
    import hashlib

    body = "Olá,\ncontrato público observado.\n"
    assert compute_copy_hash(body) == "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
