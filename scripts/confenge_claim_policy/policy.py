"""Deterministic outreach claim policy (``CLAIM_POLICY``).

Pure module: no file I/O, no network, no database, no wall clock. ``evaluated_as_of``
is always injected by the caller as a real :class:`datetime.date`.

Lifecycle vocabulary is **not** defined here. ``scripts/contracts_truth.py`` is the
single authority for contract lifecycle in this repository; this module imports its
states and its ``classify_contract_activity`` precedence instead of re-implementing a
parallel taxonomy.

Dependency direction is strictly one-way: integration modules
(``confenge_account_intelligence``, ``confenge_contact_resolution``) import this
package. This package never imports them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date

from scripts.contracts_truth import (
    ACTIVE_PROVEN,
    ACTIVITY_RULE_VERSION,
    ACTIVITY_STATES,
    CANCELLED,
    COMPLETED,
    SUSPENDED,
    TERMINATED,
    UNKNOWN,
    classify_contract_activity,
)

# --- Outreach use classes (new vocabulary — does not exist in contracts_truth) ---
CURRENT_ACTIONABLE = "CURRENT_ACTIONABLE"
RECENT_RETROSPECTIVE = "RECENT_RETROSPECTIVE"
HISTORICAL_CONTEXT = "HISTORICAL_CONTEXT"
DO_NOT_CITE = "DO_NOT_CITE"

OUTREACH_USE_CLASSES = frozenset({CURRENT_ACTIONABLE, RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT, DO_NOT_CITE})

# --- Claim modes ---
CURRENT_CONTRACT = "CURRENT_CONTRACT"
HISTORICAL_CONTRACT = "HISTORICAL_CONTRACT"
CLAIM_MODE_NONE = "NONE"

CLAIM_MODES = frozenset({CURRENT_CONTRACT, HISTORICAL_CONTRACT, CLAIM_MODE_NONE})

# --- Allowed tenses ---
PRESENT_CONFIRMED = "PRESENT_CONFIRMED"
NEUTRAL_FACTUAL = "NEUTRAL_FACTUAL"
PAST_ONLY = "PAST_ONLY"
TENSE_NONE = "NONE"

ALLOWED_TENSES = frozenset({PRESENT_CONFIRMED, NEUTRAL_FACTUAL, PAST_ONLY, TENSE_NONE})

# --- Purposes ---
PURPOSE_WHY_YOU = "why_you"
PURPOSE_WHY_NOW = "why_now"

PURPOSES = frozenset({PURPOSE_WHY_YOU, PURPOSE_WHY_NOW})

# Window (days) below which a closed/unproven contract still reads as "recent
# retrospective" rather than plain historical context. Never authorises present tense.
RECENT_RETROSPECTIVE_DAYS = 540

# Window (days) inside which a dated contractual event counts as a *contemporary*
# event. Rule 2: ACTIVE_PROVEN alone never authorises why_now — a dated
# contemporary event must also exist.
CONTEMPORARY_EVENT_DAYS = 180

COPY_HASH_PREFIX = "sha256:"

CLAIM_POLICY_VERSION = "claim-policy-v1"

# --- Reason codes ---
REASON_NO_EVIDENCE = "missing_evidence_ids"
REASON_HOLLOW_FACT = "hollow_fact"
REASON_FACTUAL_HARD_GATE = "factual_hard_gate_failed"
REASON_LIFECYCLE_DEGRADED = "lifecycle_absent_degraded_to_unknown"
REASON_LIFECYCLE_UNKNOWN = "lifecycle_unknown_present_forbidden"
REASON_LIFECYCLE_SUSPENDED = "lifecycle_suspended_not_in_execution"
REASON_LIFECYCLE_CLOSED = "lifecycle_closed_past_only"
REASON_LIFECYCLE_TERMINATED = "lifecycle_terminated_requires_explicit_evidence"
REASON_ACTIVE_PROVEN = "lifecycle_active_proven"
REASON_NO_CONTEMPORARY_EVENT = "no_contemporary_dated_event"
REASON_CONTEMPORARY_EVENT = "contemporary_dated_event"
REASON_MULTIPLE_CURRENT = "multiple_current_claims_fail_closed"
REASON_NO_CITABLE_CANDIDATE = "no_citable_candidate"
REASON_SINGLE_CURRENT = "single_current_claim"
REASON_STAMPED_STATE = "stamped_lifecycle_state"
REASON_DERIVED_STATE = "derived_lifecycle_state"
REASON_RAW_STATUS_NOT_PROMOTABLE = "raw_status_state_name_not_promotable"

# States a *textual* ``raw_status`` may adopt directly when the field already carries a
# stamped state name. ``ACTIVE_PROVEN`` is deliberately excluded: it is the only state
# that unlocks ``CURRENT_ACTIONABLE``/``PRESENT_CONFIRMED``, so it may only be reached
# through an explicit ``stamped_state=`` or through the dated-evidence path of
# ``classify_contract_activity``. Derivation demotes; it never promotes.
RAW_STATUS_FALLBACK_STATES = frozenset(ACTIVITY_STATES) - {ACTIVE_PROVEN}


@dataclass(frozen=True)
class LifecycleResolution:
    """Outcome of resolving a contract lifecycle state without touching wall clock."""

    state: str
    raw_status: str | None
    rule_version: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimCandidate:
    """A single contract considered as material for outreach copy.

    ``has_hollow_fact`` is decided by the caller (``message_spine.is_hollow_fact``
    remains the single owner of hollowness); this module never inspects text.
    """

    contract_id: str
    lifecycle_state: str = UNKNOWN
    evidence_ids: tuple[str, ...] = ()
    has_hollow_fact: bool = True
    has_contemporary_event: bool = False
    event_date: date | None = None
    lifecycle_rule_version: str = ACTIVITY_RULE_VERSION


@dataclass(frozen=True)
class ClaimPolicyResult:
    """Canonical, deterministic verdict for one claim candidate."""

    outreach_use_class: str
    claim_mode: str
    why_you_eligible: bool
    why_now_eligible: bool
    allowed_tense: str
    requires_current_authority: bool
    contract_id: str
    evidence_ids: tuple[str, ...]
    lifecycle_state: str
    evaluated_as_of: date
    reason_codes: tuple[str, ...] = ()
    copy_hash: str | None = None
    lifecycle_rule_version: str = ACTIVITY_RULE_VERSION
    policy_version: str = CLAIM_POLICY_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "outreach_use_class": self.outreach_use_class,
            "claim_mode": self.claim_mode,
            "why_you_eligible": self.why_you_eligible,
            "why_now_eligible": self.why_now_eligible,
            "allowed_tense": self.allowed_tense,
            "requires_current_authority": self.requires_current_authority,
            "contract_id": self.contract_id,
            "evidence_ids": list(self.evidence_ids),
            "lifecycle_state": self.lifecycle_state,
            "evaluated_as_of": self.evaluated_as_of.isoformat(),
            "reason_codes": list(self.reason_codes),
            "copy_hash": self.copy_hash,
            "lifecycle_rule_version": self.lifecycle_rule_version,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class MessageClaimSelection:
    """Result of applying the at-most-one-CURRENT-claim rule to a message."""

    claims: tuple[ClaimPolicyResult, ...] = ()
    reason_codes: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, object]:
        return {
            "claims": [c.as_dict() for c in self.claims],
            "reason_codes": list(self.reason_codes),
        }


def compute_copy_hash(body: str) -> str:
    """SHA256 of the exact final body string.

    Contract pinned by the architecture gate (A2): UTF-8 encoding of the string
    exactly as received — no unicode normalisation, no ``strip()``, no newline
    canonicalisation. ``story-current-claim-jit-authority-01`` pins a golden vector
    on this value.
    """
    return COPY_HASH_PREFIX + hashlib.sha256(body.encode("utf-8")).hexdigest()


def is_contemporary_event(event_date: date | None, evaluated_as_of: date) -> bool:
    """True when a dated event is recent enough to count as contemporary authority."""
    if event_date is None:
        return False
    delta = (evaluated_as_of - event_date).days
    return -CONTEMPORARY_EVENT_DAYS <= delta <= CONTEMPORARY_EVENT_DAYS


def normalize_lifecycle_state(value: object) -> str | None:
    """Return the value when it is already a stamped state of ``ACTIVITY_STATES``."""
    text = str(value or "").strip().upper()
    if text in ACTIVITY_STATES:
        return text
    return None


def resolve_lifecycle_state(
    *,
    evaluated_as_of: date,
    raw_status: object = None,
    stamped_state: object = None,
    start_date: object = None,
    end_date: object = None,
    source: str = "pncp",
    observed_at: str | None = None,
) -> LifecycleResolution:
    """Resolve a lifecycle state reusing ``contracts_truth.classify_contract_activity``.

    Architecture gate item A4: an already-stamped state never enters ``raw_status=``
    (``_norm_status`` would match 4 of 5 terminal state names by coincidence and would
    silently degrade ``ACTIVE_PROVEN``). Stamped states take a separate validated path.

    **Promotion invariant (MED-001):** ``ACTIVE_PROVEN`` is reachable only through an
    explicit ``stamped_state=`` (the validated trusted path) or through the dated
    evidence of ``classify_contract_activity``. A textual ``raw_status`` that merely
    spells a state name may adopt only the states that are safe by nature
    (``RAW_STATUS_FALLBACK_STATES``); if it spells ``ACTIVE_PROVEN`` the token is
    refused and dropped, so the vigência window decides alone. The derivation may only
    demote, never promote.
    """
    if not isinstance(evaluated_as_of, date):
        raise TypeError("evaluated_as_of must be a datetime.date")

    stamped = normalize_lifecycle_state(stamped_state)
    extra_reasons: tuple[str, ...] = ()
    if stamped is None:
        # A raw status field may already carry a stamped state name; validate first and
        # refuse anything that would promote to a present-eligible state.
        textual = normalize_lifecycle_state(raw_status)
        if textual is not None and textual in RAW_STATUS_FALLBACK_STATES:
            stamped = textual
            raw_status = None
        elif textual is not None:
            # ACTIVE_PROVEN spelled in a raw status field: refuse the promotion and let
            # classify_contract_activity decide from dated evidence only.
            raw_status = None
            extra_reasons = (REASON_RAW_STATUS_NOT_PROMOTABLE,)
    if stamped is not None:
        return LifecycleResolution(
            state=stamped,
            raw_status=None if raw_status is None else str(raw_status),
            rule_version=ACTIVITY_RULE_VERSION,
            reasons=(REASON_STAMPED_STATE,),
        )

    activity = classify_contract_activity(
        raw_status=raw_status,
        vigencia_inicio=start_date,
        vigencia_fim=end_date,
        today=evaluated_as_of,
        source=source,
        observed_at=observed_at,
    )
    return LifecycleResolution(
        state=activity.state,
        raw_status=activity.raw_status,
        rule_version=activity.rule_version,
        reasons=(REASON_DERIVED_STATE, *activity.reasons, *extra_reasons),
    )


def _is_recent(event_date: date | None, evaluated_as_of: date) -> bool:
    if event_date is None:
        return False
    return 0 <= (evaluated_as_of - event_date).days <= RECENT_RETROSPECTIVE_DAYS


def _blocked(
    candidate: ClaimCandidate,
    *,
    lifecycle_state: str,
    evaluated_as_of: date,
    reasons: tuple[str, ...],
    copy_hash: str | None,
) -> ClaimPolicyResult:
    return ClaimPolicyResult(
        outreach_use_class=DO_NOT_CITE,
        claim_mode=CLAIM_MODE_NONE,
        why_you_eligible=False,
        why_now_eligible=False,
        allowed_tense=TENSE_NONE,
        requires_current_authority=False,
        contract_id=candidate.contract_id,
        evidence_ids=tuple(candidate.evidence_ids),
        lifecycle_state=lifecycle_state,
        evaluated_as_of=evaluated_as_of,
        reason_codes=reasons,
        copy_hash=copy_hash,
        lifecycle_rule_version=candidate.lifecycle_rule_version,
    )


def evaluate_claim_policy(
    candidate: ClaimCandidate,
    *,
    evaluated_as_of: date,
    purpose: str = PURPOSE_WHY_YOU,
    copy_body: str | None = None,
) -> ClaimPolicyResult:
    """Decide how a contract may appear in outreach copy. Pure and deterministic."""
    if not isinstance(evaluated_as_of, date):
        raise TypeError("evaluated_as_of must be a datetime.date")
    if purpose not in PURPOSES:
        purpose = PURPOSE_WHY_YOU

    copy_hash = None if copy_body is None else compute_copy_hash(copy_body)

    reasons: list[str] = []
    state = normalize_lifecycle_state(candidate.lifecycle_state)
    if state is None:
        state = UNKNOWN
        reasons.append(REASON_LIFECYCLE_DEGRADED)

    # Rule 7 — factual hard gate wins over every other rule, including a favourable
    # lifecycle. No numeric score may beat it.
    has_evidence = bool(candidate.evidence_ids)
    if not has_evidence:
        reasons.append(REASON_NO_EVIDENCE)
    if candidate.has_hollow_fact:
        reasons.append(REASON_HOLLOW_FACT)
    if not has_evidence or candidate.has_hollow_fact:
        reasons.append(REASON_FACTUAL_HARD_GATE)
        return _blocked(
            candidate,
            lifecycle_state=state,
            evaluated_as_of=evaluated_as_of,
            reasons=tuple(reasons),
            copy_hash=copy_hash,
        )

    recent = _is_recent(candidate.event_date, evaluated_as_of)

    if state == ACTIVE_PROVEN:
        reasons.append(REASON_ACTIVE_PROVEN)
        why_now_eligible = bool(candidate.has_contemporary_event)
        reasons.append(REASON_CONTEMPORARY_EVENT if why_now_eligible else REASON_NO_CONTEMPORARY_EVENT)
        return ClaimPolicyResult(
            outreach_use_class=CURRENT_ACTIONABLE,
            claim_mode=CURRENT_CONTRACT,
            why_you_eligible=True,
            why_now_eligible=why_now_eligible,
            allowed_tense=PRESENT_CONFIRMED,
            # Rule 11 — CURRENT_ACTIONABLE always carries the authority requirement.
            requires_current_authority=True,
            contract_id=candidate.contract_id,
            evidence_ids=tuple(candidate.evidence_ids),
            lifecycle_state=state,
            evaluated_as_of=evaluated_as_of,
            reason_codes=tuple(reasons),
            copy_hash=copy_hash,
            lifecycle_rule_version=candidate.lifecycle_rule_version,
        )

    if state in {TERMINATED, CANCELLED}:
        # Rule 5 — default is DO_NOT_CITE; explicit evidence (already proven above by
        # the factual hard gate) unlocks past tense only.
        reasons.append(REASON_LIFECYCLE_TERMINATED)
        allowed_tense = PAST_ONLY
    elif state == COMPLETED:
        reasons.append(REASON_LIFECYCLE_CLOSED)
        allowed_tense = PAST_ONLY
    elif state == SUSPENDED:
        reasons.append(REASON_LIFECYCLE_SUSPENDED)
        allowed_tense = NEUTRAL_FACTUAL
    else:  # UNKNOWN
        reasons.append(REASON_LIFECYCLE_UNKNOWN)
        allowed_tense = NEUTRAL_FACTUAL

    reasons.append(REASON_NO_CONTEMPORARY_EVENT)
    use_class = RECENT_RETROSPECTIVE if recent else HISTORICAL_CONTEXT
    return ClaimPolicyResult(
        outreach_use_class=use_class,
        claim_mode=HISTORICAL_CONTRACT,
        # Rule 1 — history is a legitimate why_you and never requires why_now.
        why_you_eligible=True,
        why_now_eligible=False,
        allowed_tense=allowed_tense,
        requires_current_authority=False,
        contract_id=candidate.contract_id,
        evidence_ids=tuple(candidate.evidence_ids),
        lifecycle_state=state,
        evaluated_as_of=evaluated_as_of,
        reason_codes=tuple(reasons),
        copy_hash=copy_hash,
        lifecycle_rule_version=candidate.lifecycle_rule_version,
    )


def demote_to_historical(result: ClaimPolicyResult, *, reason_codes: tuple[str, ...] = ()) -> ClaimPolicyResult:
    """Rebuild a verdict as a safe historical claim (never present tense).

    Used when a CURRENT claim cannot be carried by the message (e.g. more than one
    CURRENT candidate, or missing contemporary authority). The demotion produces a
    **new** frozen result — nothing is mutated after construction (AC 26).
    """
    if result.outreach_use_class == DO_NOT_CITE:
        return result
    return ClaimPolicyResult(
        outreach_use_class=HISTORICAL_CONTEXT,
        claim_mode=HISTORICAL_CONTRACT,
        why_you_eligible=result.why_you_eligible,
        why_now_eligible=False,
        allowed_tense=NEUTRAL_FACTUAL,
        requires_current_authority=False,
        contract_id=result.contract_id,
        evidence_ids=result.evidence_ids,
        lifecycle_state=result.lifecycle_state,
        evaluated_as_of=result.evaluated_as_of,
        reason_codes=(*result.reason_codes, *reason_codes),
        copy_hash=result.copy_hash,
        lifecycle_rule_version=result.lifecycle_rule_version,
    )


def allows_present_tense(result: ClaimPolicyResult) -> bool:
    """True only when the policy authorises a present/in-execution claim."""
    return result.allowed_tense == PRESENT_CONFIRMED and result.outreach_use_class == CURRENT_ACTIONABLE


def is_tense_permitted(result: ClaimPolicyResult, tense: str) -> bool:
    """Check a candidate tense against the verdict. Unknown tenses are refused."""
    if tense not in ALLOWED_TENSES or result.allowed_tense == TENSE_NONE:
        return False
    if tense == PRESENT_CONFIRMED:
        return allows_present_tense(result)
    if tense == NEUTRAL_FACTUAL:
        return result.allowed_tense in {PRESENT_CONFIRMED, NEUTRAL_FACTUAL}
    if tense == PAST_ONLY:
        return True
    return False


def select_message_claims(results: list[ClaimPolicyResult]) -> MessageClaimSelection:
    """Apply the "at most one CURRENT claim per message" rule, fail-closed.

    Architecture gate item A3: more than one CURRENT candidate returns an **empty**
    selection plus ``reason_codes`` — never an exception. This code path feeds real
    commercial sending; raising would create a new crash surface.
    """
    currents = [r for r in results if r.outreach_use_class == CURRENT_ACTIONABLE]
    if len(currents) > 1:
        return MessageClaimSelection(claims=(), reason_codes=(REASON_MULTIPLE_CURRENT,))

    citable = tuple(r for r in results if r.outreach_use_class != DO_NOT_CITE)
    if not citable:
        return MessageClaimSelection(claims=(), reason_codes=(REASON_NO_CITABLE_CANDIDATE,))

    reasons = (REASON_SINGLE_CURRENT,) if currents else ()
    return MessageClaimSelection(claims=citable, reason_codes=reasons)
