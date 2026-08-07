"""Frozen Warmbly wire constants (mirrored from PR #4/#6 — no code import)."""

from __future__ import annotations

# Default claims that must never be asserted as confirmed demand.
DEFAULT_CLAIMS_TO_AVOID: tuple[str, ...] = (
    "garantia de economia",
    "intenção de compra confirmada",
    "lead quente",
    "propensão de compra",
    "demanda comprovada de consultoria",
)

# Dominant commercial states that must pass through unchanged.
DOMINANT_COMMERCIAL_STATES = frozenset(
    {
        "DO_NOT_CONTACT",
        "WON",
        "LOST",
        "ACTIVE_CLIENT",
    }
)

# Map Warmbly wire event_type → extra-cli commercial_state suggestion.
# WON is never applied from machine classification alone (receptor enforces).
EVENT_TO_COMMERCIAL_STATE: dict[str, str] = {
    "LEAD_IMPORTED": "NEW",
    "LEAD_REVIEWED": "REVIEWED",
    "REVIEWED": "REVIEWED",
    "CONTACT_APPROVED": "QUALIFIED",
    "CONTACTED": "CONTACTED",
    "SENT": "CONTACTED",
    "REPLIED": "REPLIED",
    "MEETING": "MEETING",
    "PROPOSAL": "PROPOSAL",
    "WON": "WON",
    "LOST": "LOST",
    "DO_NOT_CONTACT": "DO_NOT_CONTACT",
    "DNC": "DO_NOT_CONTACT",
    "BOUNCED": "CONTACTED",  # soft: bounce recorded; human may set DNC later
    "BOUNCE": "CONTACTED",
}

# Map Warmbly event → Decision Memory OutcomeType (procurement enum is not isomorphic).
# Outreach-specific detail always lives in structured_facts.
EVENT_TO_DM_OUTCOME_TYPE: dict[str, str] = {
    "LEAD_IMPORTED": "UNKNOWN",
    "LEAD_REVIEWED": "UNKNOWN",
    "REVIEWED": "UNKNOWN",
    "CONTACT_APPROVED": "UNKNOWN",
    "CONTACTED": "UNKNOWN",
    "SENT": "UNKNOWN",
    "REPLIED": "UNKNOWN",
    "MEETING": "UNKNOWN",
    "PROPOSAL": "PROPOSAL_SUBMITTED",
    "WON": "WIN",
    "LOST": "LOSS",
    "DO_NOT_CONTACT": "NO_PARTICIPATION",
    "DNC": "NO_PARTICIPATION",
    "BOUNCED": "INCIDENT",
    "BOUNCE": "INCIDENT",
}

# Channel aliases.
CHANNEL_ALIASES: dict[str, str] = {
    "email": "email",
    "mail": "email",
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "phone": "phone",
    "call": "phone",
    "linkedin": "linkedin",
    "other": "other",
    "": "unknown",
}
