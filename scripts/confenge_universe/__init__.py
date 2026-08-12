"""CONFENGE national B2G construction company universe.

Builds one canonical operational entity per private construction/engineering
economic group that appears in public contracts. Priority score is used only
for queue ordering — never as a discard gate.
"""

from __future__ import annotations

SCHEMA_VERSION = "confenge-universe-v1"
MANIFEST_VERSION = "confenge-universe-manifest-v1"
MODULE_VERSION = "1.0.0"
RULE_VERSION = "confenge-universe-rules-v1"

# Factual outreach eligibility — never commercial tiers
ELIGIBLE = "ELIGIBLE"
DNC = "DNC"
INVALID_IDENTITY = "INVALID_IDENTITY"
NOT_CONSTRUCTION = "NOT_CONSTRUCTION"
PUBLIC_ORGAN = "PUBLIC_ORGAN"
NATURAL_PERSON = "NATURAL_PERSON"
UNKNOWN_IDENTITY = "UNKNOWN_IDENTITY"

OUTREACH_ELIGIBILITY_STATES = frozenset(
    {
        ELIGIBLE,
        DNC,
        INVALID_IDENTITY,
        NOT_CONSTRUCTION,
        PUBLIC_ORGAN,
        NATURAL_PERSON,
        UNKNOWN_IDENTITY,
    }
)

# Universe membership: construction private groups (incl. DNC)
UNIVERSE_MEMBER_STATES = frozenset({ELIGIBLE, DNC})

DEFAULT_JSONL_NAME = "confenge-universe-v1.jsonl"
DEFAULT_EXCLUSIONS_JSONL_NAME = "confenge-universe-exclusions-v1.jsonl"
DEFAULT_MANIFEST_NAME = "confenge-universe-manifest-v1.json"

__all__ = [
    "SCHEMA_VERSION",
    "MANIFEST_VERSION",
    "MODULE_VERSION",
    "RULE_VERSION",
    "ELIGIBLE",
    "DNC",
    "INVALID_IDENTITY",
    "NOT_CONSTRUCTION",
    "PUBLIC_ORGAN",
    "NATURAL_PERSON",
    "UNKNOWN_IDENTITY",
    "OUTREACH_ELIGIBILITY_STATES",
    "UNIVERSE_MEMBER_STATES",
    "DEFAULT_JSONL_NAME",
    "DEFAULT_EXCLUSIONS_JSONL_NAME",
    "DEFAULT_MANIFEST_NAME",
]
