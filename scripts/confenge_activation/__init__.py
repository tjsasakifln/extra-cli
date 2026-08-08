"""Commercial activation planner for CONFENGE (extra-cli authority).

Observes the full B2G construction universe and projects a small hot set of
accounts that deserve expensive enrichment / Warmbly attention *now*.

Activation states are planning projections — not CRM commercial_state:
  WATCH | RESEARCH_REQUIRED | ACTIONABLE_NOW | SUPPRESSED

activation_score is deterministic ordering (0–100), never purchase probability.
"""

from __future__ import annotations

MODULE_VERSION = "1.0.0"
PLANNER_ID = "confenge-activation-planner"
POLICY_DEFAULT_NAME = "confenge_activation_policy.yaml"
DEFAULT_POLICY_VERSION = "confenge-activation-v1"

ACTIVATION_STATES = frozenset(
    {
        "WATCH",
        "RESEARCH_REQUIRED",
        "ACTIONABLE_NOW",
        "SUPPRESSED",
    }
)

TRIGGER_CODES = frozenset(
    {
        "NEW_RELEVANT_CONTRACT",
        "MATERIAL_PORTFOLIO_CHANGE",
        "CONTRACT_ANNIVERSARY_WINDOW",
        "NEW_AMENDMENT_OR_TERM",
        "CONTRACT_ENDING_WINDOW",
        "CONTRACT_EXTENSION_OR_PROROGATION",
        "NEW_RELEVANT_PROCESS_DOCUMENT",
        "NEW_RELEVANT_PROCUREMENT",
        "MATERIAL_CONTRACT_CHANGE",
        "RESEARCH_GAP_WORTH_RESOLVING",
    }
)

__all__ = [
    "ACTIVATION_STATES",
    "DEFAULT_POLICY_VERSION",
    "MODULE_VERSION",
    "PLANNER_ID",
    "POLICY_DEFAULT_NAME",
    "TRIGGER_CODES",
]
