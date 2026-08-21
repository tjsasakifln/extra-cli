"""Projections. Warmbly consumes classified email routes plus named-person quality.

`is_email_safe_for_warmbly` is named-person EMAIL_VALIDATED quality — not the
universal transport gate. Controlled eligibility is `controlled_email_eligible`
by route class. CALL / WhatsApp / profile / form stay upstream as manual
Decision-Unit output. This is not a second scoring of people.
"""

from __future__ import annotations

from typing import Any

from scripts.decision_unit_intelligence.controlled_email import classify_account_email_routes
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ChannelType,
    EpistemicClass,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    normalize_name,
)

WARMBLY_SCHEMA = "confenge.outreach.v1"


def associated_person_name(route: ReachabilityRoute) -> str | None:
    """Person bound to a route. ReachabilityRoute has no person_name field."""
    extra = route.extra if isinstance(route.extra, dict) else {}
    return normalize_name(extra.get("associated_person_name") or extra.get("person_name"))


def is_email_safe_for_warmbly(route: ReachabilityRoute) -> bool:
    """Named-person EMAIL_VALIDATED quality only. Not universal sendability.

    ROLE / GENERIC / PUBLIC_COMPANY_FREEMAIL use controlled_email_eligible.
    Inferred never qualifies as EMAIL_VALIDATED.
    """
    extra = route.extra or {}
    discovery = str(extra.get("email_discovery_class") or extra.get("inferred_pattern_state") or "")
    if discovery.startswith("INFERRED_PATTERN_"):
        return False
    if extra.get("inferred_grade") in {"INFERRED_HIGH", "INFERRED_UNVERIFIED"}:
        return False
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


def is_controlled_email_eligible_for_warmbly(route: ReachabilityRoute, account: AccountInvestigation) -> bool:
    """Transport-facing eligibility: allowed route class, not named-person-only."""
    ranking = classify_account_email_routes(account, named_person_safe=is_email_safe_for_warmbly)
    mailbox = str(route.channel_value or "").strip().lower()
    return any(item.mailbox == mailbox and item.controlled_email_eligible for item in ranking.classified_routes)


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
                "email_discovery_class": "EMAIL_VALIDATED",
            }
        )
    discovery_routes = []
    for route in account.routes:
        extra = route.extra or {}
        klass = extra.get("email_discovery_class")
        if not klass and route.channel_value and "@" in str(route.channel_value):
            klass = "UNKNOWN"
        if not klass:
            continue
        if klass in {
            "INFERRED_PATTERN_EMAIL",
            "INFERRED_PATTERN_MX_OK",
            "INFERRED_PATTERN_CATCH_ALL",
            "INFERRED_PATTERN_REJECTED",
            "GENERIC_MAILBOX",
            "ROLE_MAILBOX",
            "TECHNICALLY_PLAUSIBLE",
        } or str(klass).startswith("INFERRED_PATTERN_"):
            contact_tier = "CANDIDATE_UNVERIFIED"
        elif klass == "EMAIL_VALIDATED":
            contact_tier = "DIRECT_EMAIL_VALIDATED"
        else:
            contact_tier = "OBSERVED_NOT_VALIDATED"
        discovery_routes.append(
            {
                "channel_value": route.channel_value,
                "email_discovery_class": klass,
                "contact_tier": contact_tier,
                "epistemic_class": route.epistemic_class.value,
                "identity_explicitly_associated": bool(extra.get("identity_explicitly_associated")),
                "reason_codes": route.reason_codes,
            }
        )
    first_class_routes = []
    for route in account.routes:
        person = people.get(route.decision_unit_candidate_id or "")
        first_class_routes.append(
            {
                "first_class_kind": route.first_class_kind.value,
                "first_class_label": route.first_class_label.value,
                "channel_type": route.channel_type.value,
                "channel_value": route.channel_value,
                "reachability_class": route.reachability_class.value,
                "action_mode": route.action_mode.value,
                "route_relation": route.route_relation.value,
                "epistemic_class": route.epistemic_class.value,
                "freshness": route.freshness.value,
                "suppression": route.suppression.value,
                "suitability": route.suitability.value,
                "observed_at": route.observed_at,
                "source_type": route.source_type,
                "source_url": route.source_url,
                "reason_codes": route.reason_codes,
                "person_name": associated_person_name(route) or (person.person_name if person else None),
            }
        )
    ranking = classify_account_email_routes(account, named_person_safe=is_email_safe_for_warmbly)
    ranking_payload = ranking.to_dict()
    from scripts.decision_unit_intelligence.controlled_email import feed_contact_from_classified

    ranking_payload["contacts"] = [feed_contact_from_classified(item) for item in ranking.classified_routes]
    return {
        "schema_id": WARMBLY_SCHEMA,
        "account_id": account.company_entity_id,
        "cnpj": account.cnpj,
        "legal_name": account.legal_name,
        "why_now": account.why_now,
        "service_context": account.service_context,
        "recipient_candidates": recipients,
        "email_safe_count": len(recipients),
        "email_discovery_routes": discovery_routes,
        "first_class_routes": first_class_routes,
        "non_email_routes_remain_upstream": True,
        "auto_send": False,
        **ranking_payload,
    }
