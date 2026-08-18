"""Opportunity record shape for traffic-opportunity-frontier/1.0."""

from __future__ import annotations

from typing import Any

SCHEMA = "traffic-opportunity-frontier/1.0"

REQUIRED_FIELDS: tuple[str, ...] = (
    "opportunity_id",
    "question",
    "visitor_job",
    "search_intent",
    "audience",
    "funnel_stage",
    "commercial_pain",
    "offer_bridge",
    "evidence_sources",
    "geographic_scope",
    "temporal_scope",
    "grain",
    "coverage_state",
    "factual_answer_outline",
    "unique_insight",
    "calculations",
    "limitations",
    "prohibited_claims",
    "suggested_visuals",
    "suggested_internal_links",
    "suggested_cta",
    "maintenance_owner",
    "refresh_policy",
    "score_dimensions",
    "score",
    "state",
    "consumer_contract",
    "no_publication_authorization",
    "no_index_authorization",
    "epistemic",
)

FUNNEL_STAGES = frozenset({"tofu", "mofu", "bofu"})
OPPORTUNITY_STATES = frozenset({"READY", "HOLD_FOR_DATA", "REJECT"})
CAMPAIGN_STATUSES = frozenset(
    {
        "READY_FOR_WEB_CONSUMER",
        "BLOCKED_DATA_COVERAGE",
        "BLOCKED_SOURCE_ACCESS",
        "BLOCKED_CI",
    }
)

CONSUMER_CONTRACT: dict[str, Any] = {
    "consumer_id": "web-cfg/traffic-opportunity-frontier",
    "repository": "tjsasakifln/web-cfg",
    "schema": SCHEMA,
    "issues_ref": ["#65", "#73"],
    "producer_issues_ref": ["#415", "#302", "#400"],
    "no_publication_authorization": True,
    "no_index_authorization": True,
    "read_path": "exports/traffic-opportunity-frontier/v1/",
    "action": (
        "Ler o pack, redigir editorial humano a partir de top3/, "
        "passar pelo claim gate public-read antes de qualquer publicação."
    ),
}


def validate_opportunity(record: dict[str, Any]) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    errors = [f"missing:{field}" for field in missing]
    if record.get("no_publication_authorization") is not True:
        errors.append("publication_authorized")
    if record.get("no_index_authorization") is not True:
        errors.append("index_authorized")
    if record.get("state") not in OPPORTUNITY_STATES:
        errors.append("invalid_state")
    if record.get("funnel_stage") not in FUNNEL_STAGES:
        errors.append("invalid_funnel_stage")
    if not record.get("prohibited_claims"):
        errors.append("empty_prohibited_claims")
    return errors
