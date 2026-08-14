"""Projections. Warmbly gets only the email-safe subset already supported.

CALL / WhatsApp / profile / form stay upstream as manual Decision-Unit output.
This is not a second scoring of people.
"""

from __future__ import annotations

from typing import Any

from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ChannelType,
    EpistemicClass,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
)

WARMBLY_SCHEMA = "confenge.outreach.v1"


def is_email_safe_for_warmbly(route: ReachabilityRoute) -> bool:
    """Named observed corporate email only. Inferred never qualifies."""
    if route.channel_type != ChannelType.DIRECT_EMAIL:
        return False
    if route.epistemic_class != EpistemicClass.OBSERVED:
        return False
    if route.reachability_class != ReachabilityClass.R1_DIRECT:
        return False
    if route.route_relation != RouteRelation.PERSON_OWNS_CHANNEL:
        return False
    if "INFERRED" in route.reason_codes:
        return False
    return bool(route.channel_value and route.decision_unit_candidate_id)


def project_warmbly_outreach(account: AccountInvestigation) -> dict[str, Any]:
    people = {c.candidate_id: c for c in account.candidates}
    safe_routes = [r for r in account.routes if is_email_safe_for_warmbly(r)]
    recipients = []
    for route in safe_routes:
        person = people.get(route.decision_unit_candidate_id or "")
        if not person:
            continue
        recipients.append(
            {
                "candidate_id": person.candidate_id,
                "company_entity_id": account.company_entity_id,
                "person_id": person.person_id,
                "person_name": person.person_name,
                "observed_role": person.observed_roles[0] if person.observed_roles else None,
                "channel_type": "DIRECT_CORPORATE_EMAIL",
                "channel_value": route.channel_value,
                "person_channel_relation": route.route_relation.value,
                "contact_tier": "DIRECT_EMAIL_VALIDATED",
                "identity_confidence": person.identity_confidence.value,
                "channel_confidence": route.route_confidence.value,
                "outreach_suitability": person.suitability.value,
                "freshness_state": route.freshness.value,
                "ownership_status": route.ownership.value,
                "suppression_state": route.suppression.value,
                "evidence_ids": route.evidence_ids,
                "policy_version": account.policy_version,
                "reason_codes": route.reason_codes,
            }
        )
    return {
        "schema_id": WARMBLY_SCHEMA,
        "account_id": account.company_entity_id,
        "cnpj": account.cnpj,
        "legal_name": account.legal_name,
        "why_now": account.why_now,
        "service_context": account.service_context,
        "recipient_candidates": recipients,
        "email_safe_count": len(recipients),
        "non_email_routes_remain_upstream": True,
        "auto_send": False,
    }
