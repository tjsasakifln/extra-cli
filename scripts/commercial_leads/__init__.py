"""CONFENGE commercial leads queue — observable signals only, never purchase propensity."""

from __future__ import annotations

CAMPAIGN_ID = "CONFENGE-COMMERCIAL-READY-01"
MODULE_VERSION = "2.0.0-gold"

COMMERCIAL_STATES = (
    "NEW",
    "REVIEWED",
    "QUALIFIED",
    "DISQUALIFIED",
    "CONTACTED",
    "REPLIED",
    "MEETING",
    "PROPOSAL",
    "WON",
    "LOST",
    "ACTIVE_CLIENT",
    "DO_NOT_CONTACT",
)

# Terminal statuses allowed for campaign result (never RC_TECHNICAL_PASS)
TERMINAL_STATUSES = ("PASS", "BLOCKED", "FAIL")

# Legacy aliases (deprecated semantics — do not use as population claim)
POPULATION_FULL = "FULL_POPULATION"  # ambiguous; prefer explicit modes below
POPULATION_SAMPLE = "BOUNDED_SAMPLE"

# Explicit population / pipeline modes (gold standard)
DISCOVERY_PREFILTERED = "PREFILTERED_CANDIDATE_DISCOVERY"
DISCOVERY_FULL_SNAPSHOT = "FULL_SNAPSHOT_SCAN"
HISTORY_FULL_CANDIDATE = "FULL_CANDIDATE_HISTORY"
HISTORY_PREFILTER_ONLY = "PREFILTERED_ONLY_INCOMPLETE"
RANKING_FULL_ELIGIBLE = "FULL_ELIGIBLE_CANDIDATES"
RANKING_BOUNDED = "BOUNDED_SAMPLE"

SOURCE_STATE_SEPARATED = "SOURCE_STATE_SEPARATED"
SOURCE_STATE_RESTORED = "RESTORED_SNAPSHOT_SINGLE_DB"

# Discovery layer outcomes
DISCOVERY_CANDIDATE = "CANDIDATE"
DISCOVERY_NOT_CANDIDATE = "NOT_CANDIDATE"
DISCOVERY_REVIEW = "REVIEW"

CANDIDATE_DISCOVERY_RULE_VERSION = "candidate-discovery-v1"

FORBIDDEN_LANGUAGE = (
    "propensão",
    "propensao",
    "probabilidade de compra",
    "intenção de compra",
    "intencao de compra",
    "empresa interessada",
    "lead quente",
    "chance de conversão",
    "chance de conversao",
    "necessidade comprovada de consultoria",
)

__all__ = [
    "CAMPAIGN_ID",
    "MODULE_VERSION",
    "COMMERCIAL_STATES",
    "FORBIDDEN_LANGUAGE",
]
