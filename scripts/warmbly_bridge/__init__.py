"""Native Warmbly bridge: confenge.outreach.v1 exporter + confenge.outcome.v1 receptor.

Closes the integration gap between extra-cli (intelligence) and Warmbly (execution).
Does not invent facts, contacts, or commercial wins.
"""

from __future__ import annotations

SCHEMA_OUTREACH = "confenge.outreach.v1"
SCHEMA_OUTCOME = "confenge.outcome.v1"
MODULE_VERSION = "1.0.0"
DEFAULT_SYSTEM = "extra-cli"
DEFAULT_PROFILE_ID = "confenge"
DEFAULT_PROFILE_VERSION = "2.0.0"
DEFAULT_MAX_LEADS_PER_CHUNK = 50
DEFAULT_MAX_BYTES_PER_CHUNK = 512_000
DEFAULT_HMAC_SKEW_SECONDS = 300
DEFAULT_MAX_BODY_BYTES = 256_000

# Warmbly-allowed epistemic classes (mirror PR #4 constants; no code import).
EPISTEMIC_CLASSES = frozenset(
    {
        "CONFIRMED_FACT",
        "STRONG_INFERENCE",
        "WEAK_INFERENCE",
        "COMMERCIAL_HYPOTHESIS",
        "NOT_FOUND",
        "REQUIRES_COMPANY_CONFIRMATION",
        "CONTRADICTORY_EVIDENCE",
    }
)

# Warmbly-allowed contact verification statuses.
VERIFICATION_STATUSES = frozenset(
    {
        "OFFICIAL_SOURCE",
        "PUBLIC_DOCUMENT_RECENT",
        "MULTIPLE_PUBLIC_SOURCES",
        "INSTITUTIONAL_GENERIC",
        "PUBLIC_POSSIBLY_STALE",
        "CANDIDATE_UNVERIFIED",
        "NOT_FOUND",
        "INVALID",
        "BOUNCED",
        "DO_NOT_CONTACT",
    }
)

# Wire event types from Warmbly + aliases accepted by the receptor.
OUTCOME_EVENT_TYPES = frozenset(
    {
        "LEAD_IMPORTED",
        "LEAD_REVIEWED",
        "REVIEWED",
        "CONTACT_APPROVED",
        "CONTACTED",
        "SENT",
        "REPLIED",
        "MEETING",
        "PROPOSAL",
        "WON",
        "LOST",
        "DO_NOT_CONTACT",
        "DNC",
        "BOUNCED",
        "BOUNCE",
    }
)

# Required top-level feed fields (Warmbly PR #4 Feed struct).
REQUIRED_FEED_FIELDS = (
    "schema_version",
    "generated_at",
    "source",
    "pagination",
    "leads",
)

REQUIRED_SOURCE_FIELDS = (
    "system",
    "run_id",
    "snapshot_hash",
    "profile_id",
    "profile_version",
)

REQUIRED_LEAD_FIELDS = (
    "source_lead_id",
    "company",
    "priority",
    "moment",
    "offer",
    "messaging_context",
    "contacts",
    "contracts",
    "evidence",
    "commercial_state",
)

REQUIRED_COMPANY_FIELDS = ("cnpj14",)
REQUIRED_MESSAGING_FIELDS = (
    "fact_to_mention",
    "question_to_ask",
    "cta",
    "claims_to_avoid",
)

__all__ = [
    "SCHEMA_OUTREACH",
    "SCHEMA_OUTCOME",
    "MODULE_VERSION",
    "REQUIRED_FEED_FIELDS",
    "REQUIRED_LEAD_FIELDS",
    "EPISTEMIC_CLASSES",
    "OUTCOME_EVENT_TYPES",
]
