"""Claim-safety policy constants.

Single source of truth for the policy version, the five safety classes and the
reason codes emitted by the audit. Nothing here duplicates ``contracts_truth``
activity tokens or enums — those are imported, never restated.
"""

from __future__ import annotations

CLAIM_SAFETY_POLICY_VERSION = "confenge-claim-safety-v1"
CLAIM_SAFETY_CORPUS_HASH_ALGORITHM = "sha256"

# --- the five classes -------------------------------------------------------
SAFE_NO_CURRENT_CLAIM = "SAFE_NO_CURRENT_CLAIM"
SAFE_CURRENT_PROVEN = "SAFE_CURRENT_PROVEN"
SAFE_HISTORICAL = "SAFE_HISTORICAL"
UNSAFE_PRESENT_CLAIM = "UNSAFE_PRESENT_CLAIM"
NEEDS_RESEARCH = "NEEDS_RESEARCH"

CLAIM_SAFETY_CLASSES = (
    SAFE_NO_CURRENT_CLAIM,
    SAFE_CURRENT_PROVEN,
    SAFE_HISTORICAL,
    UNSAFE_PRESENT_CLAIM,
    NEEDS_RESEARCH,
)

# Only these are publishable. ``NEEDS_RESEARCH`` is deliberately absent: a
# template we could not read is never a terminal, publishable state (AC 20).
PUBLISHABLE_CLASSES = frozenset({SAFE_NO_CURRENT_CLAIM, SAFE_CURRENT_PROVEN, SAFE_HISTORICAL})

# --- reason codes -----------------------------------------------------------
REASON_ACTIVE_PROVEN_UNREACHABLE = "active_proven_unreachable_from_published_payload"
REASON_UNRECOGNIZED_TEMPLATE = "unrecognized_why_now_template"
REASON_AMBIGUOUS_TEMPLATE = "ambiguous_why_now_template"
REASON_NO_LINKED_CONTRACT = "present_claim_without_linked_contract"
REASON_ACTIVITY_NOT_PROVEN = "present_claim_over_unproven_activity"
REASON_POLICY_AUTHORED_COPY = "policy_authored_copy"
REASON_PAST_FRAME_ANCHORED = "past_frame_anchored_on_end_date"

# Marker written into a lead by ``rewrite.py``. Its presence means the copy is no
# longer the generator's ambiguous template but a deterministic, policy-authored
# rendering whose claim surface is re-verified lexically on every classification.
CLAIM_SAFETY_LEAD_KEY = "claim_safety"
POLICY_AUTHORED_COPY_KEY = "policy_authored_copy"

__all__ = [
    "CLAIM_SAFETY_CLASSES",
    "CLAIM_SAFETY_CORPUS_HASH_ALGORITHM",
    "CLAIM_SAFETY_LEAD_KEY",
    "CLAIM_SAFETY_POLICY_VERSION",
    "NEEDS_RESEARCH",
    "POLICY_AUTHORED_COPY_KEY",
    "PUBLISHABLE_CLASSES",
    "REASON_ACTIVE_PROVEN_UNREACHABLE",
    "REASON_ACTIVITY_NOT_PROVEN",
    "REASON_AMBIGUOUS_TEMPLATE",
    "REASON_NO_LINKED_CONTRACT",
    "REASON_PAST_FRAME_ANCHORED",
    "REASON_POLICY_AUTHORED_COPY",
    "REASON_UNRECOGNIZED_TEMPLATE",
    "SAFE_CURRENT_PROVEN",
    "SAFE_HISTORICAL",
    "SAFE_NO_CURRENT_CLAIM",
    "UNSAFE_PRESENT_CLAIM",
]
