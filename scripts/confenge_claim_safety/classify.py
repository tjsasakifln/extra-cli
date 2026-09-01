"""The five claim-safety classes.

Axis 1 — the claim asserted by the *template*, read off the evidence-stripped
assertion surface (``claim_surface``).
Axis 2 — the real ``activity_state`` of the linked contract, obtained from
``scripts.contracts_truth.classify_contract_activity``. That module is READ-ONLY
here: its enums and tokens are imported, never redefined, never extended and
never promoted.

Fail-closed everywhere. ``UNKNOWN`` activity under a present claim is UNSAFE.
A ``why_now_code`` this module does not recognize is ``NEEDS_RESEARCH``, never a
``SAFE_*`` class by omission (AC 20).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from scripts.confenge_claim_safety.claim_surface import (
    CLAIM_NONE,
    CLAIM_PAST,
    CLAIM_PRESENT,
    lead_claim,
)
from scripts.confenge_claim_safety.policy import (
    CLAIM_SAFETY_CLASSES,
    CLAIM_SAFETY_LEAD_KEY,
    CLAIM_SAFETY_POLICY_VERSION,
    NEEDS_RESEARCH,
    POLICY_AUTHORED_COPY_KEY,
    REASON_ACTIVE_PROVEN_UNREACHABLE,
    REASON_ACTIVITY_NOT_PROVEN,
    REASON_AMBIGUOUS_TEMPLATE,
    REASON_NO_LINKED_CONTRACT,
    REASON_PAST_FRAME_ANCHORED,
    REASON_POLICY_AUTHORED_COPY,
    REASON_UNRECOGNIZED_TEMPLATE,
    SAFE_CURRENT_PROVEN,
    SAFE_HISTORICAL,
    SAFE_NO_CURRENT_CLAIM,
    UNSAFE_PRESENT_CLAIM,
)
from scripts.contracts_truth import ACTIVE_PROVEN, classify_contract_activity

# The ``why_now`` triggers this module knows how to read. The triggers are
# produced lowercase by ``facts.py::why_now`` and uppercased downstream in
# ``scripts/confenge_outreach_pipeline/adapt.py``. There is no enum in code, so
# the set below is *fixed against* ``facts.py`` and pinned by the drift test
# ``tests/confenge_claim_safety/test_template_set_drift.py`` (AC 21): adding a
# seventh trigger breaks that test instead of shipping unclassified.
RECOGNIZED_WHY_NOW_CODES = frozenset(
    {
        "ADDENDUM",
        "GLOSA_MEDICAO",
        "REEQUILIBRIO",
        "MATURE_NO_REAJUSTE",
        "INSUFFICIENT_FACTS",
        "PORTFOLIO_REVIEW",
    }
)

# Recognized but deliberately not resolvable to a SAFE_* class. The
# MATURE_NO_REAJUSTE template ("Contrato maduro (com data de início observada)
# sem prova de reajuste no input — janela potencial de reajuste") is genuinely
# ambiguous between a present claim and none; a fail-closed story does not
# resolve ambiguity in favour of safe. Promoting it requires its own copy story
# (@po Decisão nº 1).
AMBIGUOUS_WHY_NOW_CODES = frozenset({"MATURE_NO_REAJUSTE"})

# Shortest object prefix that still identifies one contract in the payload.
MIN_CONTRACT_LINK_PREFIX = 24

_OBJETO_PREFIX = re.compile(r"objeto\s*:\s*(.+?)(?:;|$)", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ClaimSafetyResult:
    """Outcome of classifying one published lead."""

    safety_class: str
    claim: str
    why_now_code: str
    surface: str
    contract_id: str | None = None
    activity_state: str | None = None
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "safety_class": self.safety_class,
            "claim": self.claim,
            "why_now_code": self.why_now_code,
            "contract_id": self.contract_id,
            "activity_state": self.activity_state,
            "reason_codes": list(self.reason_codes),
            "policy_version": CLAIM_SAFETY_POLICY_VERSION,
        }


def why_now_code(lead: dict[str, Any]) -> str:
    """Uppercased ``why_now`` trigger carried by the published lead."""
    messaging = lead.get("messaging_context") if isinstance(lead.get("messaging_context"), dict) else {}
    code = messaging.get("why_now_code")
    if not code:
        moment = lead.get("moment") if isinstance(lead.get("moment"), dict) else {}
        code = moment.get("code")
    return str(code or "").strip().upper()


def _is_policy_authored(lead: dict[str, Any]) -> bool:
    block = lead.get(CLAIM_SAFETY_LEAD_KEY)
    return isinstance(block, dict) and block.get(POLICY_AUTHORED_COPY_KEY) is True


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def link_contract(lead: dict[str, Any]) -> dict[str, Any] | None:
    """The specific payload contract the copy speaks about, or ``None``.

    The generator quotes the chosen contract's ``object`` (truncated) into
    ``fact_to_mention``; the link is therefore the contract with the longest
    matching object prefix. A lead whose copy cannot be bound to one contract is
    not silently bound to an arbitrary one — it stays unlinked, which under a
    present claim means ``NEEDS_RESEARCH`` (AC 5).
    """
    contracts = [item for item in (lead.get("contracts") or []) if isinstance(item, dict)]
    if not contracts:
        return None
    messaging = lead.get("messaging_context") if isinstance(lead.get("messaging_context"), dict) else {}
    match = _OBJETO_PREFIX.search(str(messaging.get("fact_to_mention") or ""))
    quoted = (match.group(1).strip() if match else "").rstrip("…").strip()
    if quoted:
        best: dict[str, Any] | None = None
        best_length = 0
        for contract in contracts:
            obj = str(contract.get("object") or contract.get("objeto") or "").strip()
            length = _common_prefix_length(quoted, obj)
            if length > best_length:
                best, best_length = contract, length
        if best is not None and best_length >= MIN_CONTRACT_LINK_PREFIX:
            return best
    if len(contracts) == 1:
        return contracts[0]
    return None


def _contract_activity_state(contract: dict[str, Any], *, today: date | None) -> str:
    activity = classify_contract_activity(
        raw_status=contract.get("status") or contract.get("situacao"),
        vigencia_inicio=contract.get("start_date") or contract.get("vigencia_inicio"),
        vigencia_fim=contract.get("end_date") or contract.get("vigencia_fim"),
        today=today,
        source=str(contract.get("source") or "pncp"),
        observed_at=contract.get("observed_at"),
    )
    return activity.state


def classify_lead(lead: dict[str, Any], *, today: date | None = None) -> ClaimSafetyResult:
    """Classify one published lead into exactly one of the five classes."""
    code = why_now_code(lead)
    claim, surface = lead_claim(lead)
    policy_authored = _is_policy_authored(lead)

    if not policy_authored:
        if code not in RECOGNIZED_WHY_NOW_CODES:
            return ClaimSafetyResult(
                safety_class=NEEDS_RESEARCH,
                claim=claim,
                why_now_code=code,
                surface=surface,
                reason_codes=(REASON_UNRECOGNIZED_TEMPLATE,),
            )
        if code in AMBIGUOUS_WHY_NOW_CODES:
            return ClaimSafetyResult(
                safety_class=NEEDS_RESEARCH,
                claim=claim,
                why_now_code=code,
                surface=surface,
                reason_codes=(REASON_AMBIGUOUS_TEMPLATE,),
            )

    base_reasons: tuple[str, ...] = (REASON_POLICY_AUTHORED_COPY,) if policy_authored else ()

    if claim == CLAIM_NONE:
        return ClaimSafetyResult(
            safety_class=SAFE_NO_CURRENT_CLAIM,
            claim=claim,
            why_now_code=code,
            surface=surface,
            reason_codes=base_reasons,
        )

    if claim == CLAIM_PAST:
        return ClaimSafetyResult(
            safety_class=SAFE_HISTORICAL,
            claim=claim,
            why_now_code=code,
            surface=surface,
            reason_codes=base_reasons + (REASON_PAST_FRAME_ANCHORED,),
        )

    # claim == CLAIM_PRESENT — it must be proven against the Contract Truth.
    contract = link_contract(lead)
    if contract is None:
        return ClaimSafetyResult(
            safety_class=NEEDS_RESEARCH,
            claim=claim,
            why_now_code=code,
            surface=surface,
            reason_codes=base_reasons + (REASON_NO_LINKED_CONTRACT,),
        )
    state = _contract_activity_state(contract, today=today)
    contract_id = str(contract.get("id") or "") or None
    if state == ACTIVE_PROVEN:
        return ClaimSafetyResult(
            safety_class=SAFE_CURRENT_PROVEN,
            claim=claim,
            why_now_code=code,
            surface=surface,
            contract_id=contract_id,
            activity_state=state,
            reason_codes=base_reasons,
        )
    return ClaimSafetyResult(
        safety_class=UNSAFE_PRESENT_CLAIM,
        claim=claim,
        why_now_code=code,
        surface=surface,
        contract_id=contract_id,
        activity_state=state,
        reason_codes=base_reasons + (REASON_ACTIVITY_NOT_PROVEN,),
    )


def class_distribution(results: list[ClaimSafetyResult]) -> dict[str, int]:
    """Counts per class, with every class always present (0 is reported, never hidden)."""
    counts = Counter(result.safety_class for result in results)
    return {name: int(counts.get(name, 0)) for name in CLAIM_SAFETY_CLASSES}


def active_proven_reason_codes(results: list[ClaimSafetyResult]) -> list[str]:
    """Explain a zero ``SAFE_CURRENT_PROVEN`` count instead of silencing it (AC 2)."""
    if any(result.safety_class == SAFE_CURRENT_PROVEN for result in results):
        return []
    return [REASON_ACTIVE_PROVEN_UNREACHABLE]


__all__ = [
    "AMBIGUOUS_WHY_NOW_CODES",
    "CLAIM_NONE",
    "CLAIM_PAST",
    "CLAIM_PRESENT",
    "MIN_CONTRACT_LINK_PREFIX",
    "RECOGNIZED_WHY_NOW_CODES",
    "ClaimSafetyResult",
    "active_proven_reason_codes",
    "class_distribution",
    "classify_lead",
    "link_contract",
    "why_now_code",
]
