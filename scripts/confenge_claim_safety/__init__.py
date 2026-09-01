"""Claim safety for the CONFENGE outbound feed.

No published lead may assert, in commercial copy, that a public contract is
current ("ativo", "vigente", "em execução") unless that assertion is backed by
the real ``activity_state`` from ``scripts.contracts_truth``. Absence of proof is
never promoted to safe.

Modules:
  ``policy``        — policy version, the five classes, reason codes
  ``claim_surface`` — assertion surface with interpolated evidence removed
  ``classify``      — the five classes (claim × activity_state)
  ``rewrite``       — deterministic rewrite of unsafe / unreadable claims
"""

from __future__ import annotations

from scripts.confenge_claim_safety.policy import (
    CLAIM_SAFETY_CLASSES,
    CLAIM_SAFETY_POLICY_VERSION,
    NEEDS_RESEARCH,
    PUBLISHABLE_CLASSES,
    SAFE_CURRENT_PROVEN,
    SAFE_HISTORICAL,
    SAFE_NO_CURRENT_CLAIM,
    UNSAFE_PRESENT_CLAIM,
)

__all__ = [
    "CLAIM_SAFETY_CLASSES",
    "CLAIM_SAFETY_POLICY_VERSION",
    "NEEDS_RESEARCH",
    "PUBLISHABLE_CLASSES",
    "SAFE_CURRENT_PROVEN",
    "SAFE_HISTORICAL",
    "SAFE_NO_CURRENT_CLAIM",
    "UNSAFE_PRESENT_CLAIM",
]
