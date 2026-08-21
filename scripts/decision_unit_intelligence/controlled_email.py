"""Controlled email eligibility by route class.

Identity quality (`EMAIL_VALIDATED`, named-person evidence) stays a separate
signal from transport eligibility. ROLE / GENERIC / PUBLIC_COMPANY_FREEMAIL
may be controlled-eligible without a fabricated person and without promotion
to EMAIL_VALIDATED. PROBABILISTIC_OR_RISKY stays out of the default policy.

This module never grants auto-send.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from scripts.confenge_contact_resolution.mailbox_purpose import (
    CONTROLLED_BLOCKED_PURPOSES,
    classify_mailbox_purpose,
)
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ChannelType,
    DecisionUnitCandidate,
    EpistemicClass,
    FreshnessState,
    OwnershipStatus,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
)
from scripts.decision_unit_intelligence.reachability import (
    is_brand_mailbox,
    is_freemail,
    is_generic_mailbox,
    is_role_mailbox,
    looks_nominal_local,
)

CONTROLLED_EMAIL_POLICY_VERSION = "controlled-email-policy.v1"
CONTROLLED_EMAIL_SCHEMA_VERSION = "confenge.outreach.controlled_email.v1"

EVIDENCE_OBSERVED = "OBSERVED"
EVIDENCE_UNKNOWN = "UNKNOWN"

COMPANY_ASSOCIATION_SOURCES = frozenset(
    {
        "company_website",
        "company_site",
        "official_documents",
        "official_document",
        "company_registry",
        "site",
        "institutional_site",
    }
)

EMAIL_CHANNEL_TYPES = frozenset(
    {
        ChannelType.DIRECT_EMAIL,
        ChannelType.INFERRED_DIRECT_EMAIL,
        ChannelType.ROLE_MAILBOX,
        ChannelType.GENERIC_CORPORATE_EMAIL,
    }
)


class EmailRouteClass(StrEnum):
    DIRECT_PERSON = "DIRECT_PERSON"
    ROLE_OR_DEPARTMENT = "ROLE_OR_DEPARTMENT"
    GENERIC_COMPANY = "GENERIC_COMPANY"
    PUBLIC_COMPANY_FREEMAIL = "PUBLIC_COMPANY_FREEMAIL"
    PROBABILISTIC_OR_RISKY = "PROBABILISTIC_OR_RISKY"


class ControlledRiskClass(StrEnum):
    ALLOWED = "ALLOWED"
    RISKY = "RISKY"


DEFAULT_PILOT_ROUTE_CLASSES: frozenset[EmailRouteClass] = frozenset(
    {
        EmailRouteClass.DIRECT_PERSON,
        EmailRouteClass.ROLE_OR_DEPARTMENT,
        EmailRouteClass.GENERIC_COMPANY,
        EmailRouteClass.PUBLIC_COMPANY_FREEMAIL,
    }
)

ROUTE_CLASS_RANK: dict[EmailRouteClass, int] = {
    EmailRouteClass.DIRECT_PERSON: 1,
    EmailRouteClass.ROLE_OR_DEPARTMENT: 2,
    EmailRouteClass.GENERIC_COMPANY: 3,
    EmailRouteClass.PUBLIC_COMPANY_FREEMAIL: 4,
    EmailRouteClass.PROBABILISTIC_OR_RISKY: 99,
}


@dataclass(frozen=True)
class ClassifiedEmailRoute:
    """One classified mailbox on an account. Never invents a person."""

    canonical_account_id: str
    mailbox: str
    route_class: EmailRouteClass
    provenance: str
    source: str | None
    observed_at: str | None
    freshness: str
    epistemic_class: str
    mailbox_company_evidence: str
    mailbox_department_evidence: str
    mailbox_person_evidence: str
    role_confidence: str
    risk_class: ControlledRiskClass
    suppression_state: str
    preferred_rank: int | None
    preferred_initial: bool
    controlled_email_eligible: bool
    reason_codes: tuple[str, ...]
    policy_version: str = CONTROLLED_EMAIL_POLICY_VERSION
    schema_version: str = CONTROLLED_EMAIL_SCHEMA_VERSION
    person_id: str | None = None
    person_name: str | None = None
    email_validated: bool = False
    route_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_account_id": self.canonical_account_id,
            "mailbox": self.mailbox,
            "route_class": self.route_class.value,
            "provenance": self.provenance,
            "source": self.source,
            "observed_at": self.observed_at,
            "freshness": self.freshness,
            "epistemic_class": self.epistemic_class,
            "mailbox_company_evidence": self.mailbox_company_evidence,
            "mailbox_department_evidence": self.mailbox_department_evidence,
            "mailbox_person_evidence": self.mailbox_person_evidence,
            "role_confidence": self.role_confidence,
            "risk_class": self.risk_class.value,
            "suppression_state": self.suppression_state,
            "preferred_rank": self.preferred_rank,
            "preferred_initial": self.preferred_initial,
            "controlled_email_eligible": self.controlled_email_eligible,
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "person_id": self.person_id,
            "person_name": self.person_name,
            "email_validated": self.email_validated,
            "route_id": self.route_id,
        }


@dataclass(frozen=True)
class AccountEmailRanking:
    classified_routes: tuple[ClassifiedEmailRoute, ...]
    preferred_initial_route: ClassifiedEmailRoute | None
    alternative_routes: tuple[ClassifiedEmailRoute, ...]
    policy_version: str = CONTROLLED_EMAIL_POLICY_VERSION
    schema_version: str = CONTROLLED_EMAIL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        preferred = self.preferred_initial_route.to_dict() if self.preferred_initial_route else None
        return {
            "classified_email_routes": [r.to_dict() for r in self.classified_routes],
            "preferred_initial_route": preferred,
            "alternative_email_routes": [r.to_dict() for r in self.alternative_routes],
            "controlled_email_eligible_count": sum(1 for r in self.classified_routes if r.controlled_email_eligible),
            "controlled_email_policy_version": self.policy_version,
            "controlled_email_schema_version": self.schema_version,
        }


def is_email_channel(route: ReachabilityRoute) -> bool:
    if route.channel_type in EMAIL_CHANNEL_TYPES:
        return True
    value = str(route.channel_value or "")
    return "@" in value and "." in value.split("@", 1)[-1]


def _discovery_class(route: ReachabilityRoute) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    return str(extra.get("email_discovery_class") or extra.get("inferred_pattern_state") or "")


def _is_inferred_or_catch_all(route: ReachabilityRoute) -> bool:
    extra = route.extra if isinstance(route.extra, dict) else {}
    discovery = _discovery_class(route)
    if route.channel_type == ChannelType.INFERRED_DIRECT_EMAIL:
        return True
    if route.epistemic_class == EpistemicClass.INFERRED:
        return True
    if discovery.startswith("INFERRED_PATTERN_"):
        return True
    if extra.get("inferred_grade") in {"INFERRED_HIGH", "INFERRED_UNVERIFIED"}:
        return True
    if "INFERRED" in (route.reason_codes or ()):
        return True
    if extra.get("catch_all_inconclusive") is True:
        return True
    if extra.get("mx_catch_all") in {True, "INCONCLUSIVE", "CATCH_ALL"}:
        return True
    if discovery == "INFERRED_PATTERN_CATCH_ALL":
        return True
    if discovery == "TECHNICALLY_PLAUSIBLE":
        return True
    return False


def mailbox_company_evidence(route: ReachabilityRoute) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    explicit = str(extra.get("mailbox_company_evidence") or "").upper()
    if explicit in {EVIDENCE_OBSERVED, EVIDENCE_UNKNOWN}:
        return explicit
    if extra.get("company_associated") is True:
        return EVIDENCE_OBSERVED
    if extra.get("mailbox_associated_to_company") is True:
        return EVIDENCE_OBSERVED
    if route.ownership == OwnershipStatus.COMPANY_OWNED:
        return EVIDENCE_OBSERVED
    source = str(route.source_type or "").lower()
    if source in COMPANY_ASSOCIATION_SOURCES:
        return EVIDENCE_OBSERVED
    if extra.get("identity_explicitly_associated") is True and not is_freemail(route.channel_value):
        return EVIDENCE_OBSERVED
    return EVIDENCE_UNKNOWN


def mailbox_department_evidence(route: ReachabilityRoute) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    explicit = str(extra.get("mailbox_department_evidence") or "").upper()
    if explicit in {EVIDENCE_OBSERVED, EVIDENCE_UNKNOWN}:
        return explicit
    if route.route_relation == RouteRelation.ROUTES_TO_ROLE:
        return EVIDENCE_OBSERVED
    if is_role_mailbox(route.channel_value) or route.channel_type == ChannelType.ROLE_MAILBOX:
        return EVIDENCE_OBSERVED
    if route.target_role:
        return EVIDENCE_OBSERVED
    return EVIDENCE_UNKNOWN


def mailbox_person_evidence(route: ReachabilityRoute, person: DecisionUnitCandidate | None) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    explicit = str(extra.get("mailbox_person_evidence") or "").upper()
    if explicit in {EVIDENCE_OBSERVED, EVIDENCE_UNKNOWN}:
        return explicit
    if extra.get("identity_explicitly_associated") is True and person and person.person_name:
        return EVIDENCE_OBSERVED
    if route.route_relation == RouteRelation.PERSON_OWNS_CHANNEL and person and person.person_name:
        return EVIDENCE_OBSERVED
    return EVIDENCE_UNKNOWN


def classify_email_route_class(
    route: ReachabilityRoute,
    *,
    person: DecisionUnitCandidate | None = None,
) -> EmailRouteClass:
    """Map one email route to a controlled-outreach class. Does not mint people."""
    if _is_inferred_or_catch_all(route):
        return EmailRouteClass.PROBABILISTIC_OR_RISKY

    value = route.channel_value
    company_ev = mailbox_company_evidence(route)
    person_ev = mailbox_person_evidence(route, person)
    discovery = _discovery_class(route)

    if is_freemail(value):
        if company_ev == EVIDENCE_OBSERVED:
            return EmailRouteClass.PUBLIC_COMPANY_FREEMAIL
        return EmailRouteClass.PROBABILISTIC_OR_RISKY

    if (
        is_role_mailbox(value)
        or route.channel_type == ChannelType.ROLE_MAILBOX
        or discovery == "ROLE_MAILBOX"
        or route.route_relation == RouteRelation.ROUTES_TO_ROLE
    ):
        return EmailRouteClass.ROLE_OR_DEPARTMENT

    if (
        is_generic_mailbox(value)
        or is_brand_mailbox(value)
        or route.channel_type == ChannelType.GENERIC_CORPORATE_EMAIL
        or discovery == "GENERIC_MAILBOX"
    ):
        return EmailRouteClass.GENERIC_COMPANY

    if person_ev == EVIDENCE_OBSERVED and person and person.person_name:
        return EmailRouteClass.DIRECT_PERSON

    if looks_nominal_local(value) and person_ev != EVIDENCE_OBSERVED:
        return EmailRouteClass.PROBABILISTIC_OR_RISKY

    if company_ev == EVIDENCE_OBSERVED:
        return EmailRouteClass.GENERIC_COMPANY
    return EmailRouteClass.PROBABILISTIC_OR_RISKY


def _provenance_label(route: ReachabilityRoute, route_class: EmailRouteClass) -> str:
    if route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY:
        if route.epistemic_class == EpistemicClass.INFERRED or _is_inferred_or_catch_all(route):
            return EpistemicClass.INFERRED.value
        if is_freemail(route.channel_value) and mailbox_company_evidence(route) != EVIDENCE_OBSERVED:
            return "UNKNOWN"
        return "RISKY"
    if route.epistemic_class == EpistemicClass.OBSERVED:
        return EpistemicClass.OBSERVED.value
    if route.epistemic_class == EpistemicClass.INFERRED:
        return EpistemicClass.INFERRED.value
    return route.epistemic_class.value


def _role_confidence(route: ReachabilityRoute, person: DecisionUnitCandidate | None) -> str:
    if person and person.role_confidence:
        return person.role_confidence.value
    if mailbox_department_evidence(route) == EVIDENCE_OBSERVED:
        return "MEDIUM"
    return EVIDENCE_UNKNOWN


def evaluate_controlled_email_eligible(
    route: ReachabilityRoute,
    *,
    person: DecisionUnitCandidate | None = None,
    allowed_classes: frozenset[EmailRouteClass] = DEFAULT_PILOT_ROUTE_CLASSES,
    named_person_safe: bool = False,
) -> ClassifiedEmailRoute:
    """Decide controlled eligibility for one mailbox. Named-person is not universal."""
    extra = route.extra if isinstance(route.extra, dict) else {}
    mailbox = str(route.channel_value or "").strip().lower()
    route_class = classify_email_route_class(route, person=person)
    company_ev = mailbox_company_evidence(route)
    department_ev = mailbox_department_evidence(route)
    person_ev = mailbox_person_evidence(route, person)
    suppression = route.suppression.value if route.suppression else SuppressionState.NONE.value
    freshness = route.freshness.value if route.freshness else FreshnessState.UNKNOWN.value
    reasons: list[str] = [f"route_class:{route_class.value}"]
    risk = (
        ControlledRiskClass.RISKY
        if route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
        else ControlledRiskClass.ALLOWED
    )

    eligible = True
    if not mailbox or "@" not in mailbox:
        eligible = False
        reasons.append("mailbox_missing")
    purpose = classify_mailbox_purpose(mailbox)
    if purpose.purpose in CONTROLLED_BLOCKED_PURPOSES:
        eligible = False
        reasons.append(purpose.block_reason or f"mailbox_purpose_blocked:{purpose.purpose}")
    if suppression != SuppressionState.NONE.value:
        eligible = False
        reasons.append(f"suppressed:{suppression}")
        if suppression == SuppressionState.OPT_OUT.value:
            reasons.append("opt_out")
        if suppression == SuppressionState.HARD_BOUNCE.value:
            reasons.append("hard_bounce")
        if suppression == SuppressionState.DNC.value:
            reasons.append("dnc")
    if extra.get("opt_out") is True:
        eligible = False
        reasons.append("opt_out")
    if freshness == FreshnessState.STALE.value:
        eligible = False
        reasons.append("stale")
    if route_class not in allowed_classes:
        eligible = False
        reasons.append("route_class_outside_default_pilot")
    if route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY:
        eligible = False
        reasons.append("risky_excluded_from_default_pilot")
        if is_freemail(mailbox) and company_ev != EVIDENCE_OBSERVED:
            reasons.append("unassociated_freemail")
        if _is_inferred_or_catch_all(route):
            reasons.append("inferred_or_catch_all")
    if route.epistemic_class == EpistemicClass.INFERRED:
        eligible = False
        reasons.append("inferred_cannot_be_observed")
    if company_ev != EVIDENCE_OBSERVED:
        eligible = False
        reasons.append("mailbox_company_evidence_unknown")
    if route_class == EmailRouteClass.DIRECT_PERSON and person_ev != EVIDENCE_OBSERVED:
        eligible = False
        reasons.append("direct_person_requires_named_person_evidence")
    if route_class == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL and company_ev != EVIDENCE_OBSERVED:
        eligible = False
        reasons.append("freemail_requires_company_association")

    person_id = None
    person_name = None
    if route_class == EmailRouteClass.DIRECT_PERSON and person_ev == EVIDENCE_OBSERVED and person:
        person_id = person.person_id
        person_name = person.person_name
        reasons.append("named_person_evidence_present")
    else:
        reasons.append("person_unknown")

    if eligible:
        reasons.append("controlled_email_eligible")

    return ClassifiedEmailRoute(
        canonical_account_id=route.company_entity_id,
        mailbox=mailbox,
        route_class=route_class,
        provenance=_provenance_label(route, route_class),
        source=route.source_type,
        observed_at=route.observed_at,
        freshness=freshness,
        epistemic_class=route.epistemic_class.value,
        mailbox_company_evidence=company_ev,
        mailbox_department_evidence=department_ev,
        mailbox_person_evidence=person_ev,
        role_confidence=_role_confidence(route, person),
        risk_class=risk,
        suppression_state=suppression,
        preferred_rank=None,
        preferred_initial=False,
        controlled_email_eligible=eligible,
        reason_codes=tuple(reasons),
        person_id=person_id,
        person_name=person_name,
        email_validated=bool(named_person_safe and route_class == EmailRouteClass.DIRECT_PERSON),
        route_id=route.route_id,
    )


def _sort_key(item: ClassifiedEmailRoute) -> tuple[int, int, str]:
    class_rank = ROUTE_CLASS_RANK.get(item.route_class, 99)
    purpose_rank = classify_mailbox_purpose(item.mailbox).rank
    return (class_rank, purpose_rank, item.mailbox)


def rank_account_email_routes(
    classified: list[ClassifiedEmailRoute],
) -> AccountEmailRanking:
    """Publish exactly one preferred initial route. Alternatives are not shotgun."""
    eligible = [c for c in classified if c.controlled_email_eligible]
    eligible_sorted = sorted(eligible, key=_sort_key)
    ineligible = [c for c in classified if not c.controlled_email_eligible]
    ranked: list[ClassifiedEmailRoute] = []
    preferred: ClassifiedEmailRoute | None = None
    alternatives: list[ClassifiedEmailRoute] = []
    for index, item in enumerate(eligible_sorted, start=1):
        is_preferred = index == 1
        updated = ClassifiedEmailRoute(
            canonical_account_id=item.canonical_account_id,
            mailbox=item.mailbox,
            route_class=item.route_class,
            provenance=item.provenance,
            source=item.source,
            observed_at=item.observed_at,
            freshness=item.freshness,
            epistemic_class=item.epistemic_class,
            mailbox_company_evidence=item.mailbox_company_evidence,
            mailbox_department_evidence=item.mailbox_department_evidence,
            mailbox_person_evidence=item.mailbox_person_evidence,
            role_confidence=item.role_confidence,
            risk_class=item.risk_class,
            suppression_state=item.suppression_state,
            preferred_rank=index,
            preferred_initial=is_preferred,
            controlled_email_eligible=item.controlled_email_eligible,
            reason_codes=item.reason_codes + (("preferred_initial_route",) if is_preferred else ("alternative_route",)),
            policy_version=item.policy_version,
            schema_version=item.schema_version,
            person_id=item.person_id,
            person_name=item.person_name,
            email_validated=item.email_validated,
            route_id=item.route_id,
        )
        ranked.append(updated)
        if is_preferred:
            preferred = updated
        else:
            alternatives.append(updated)
    all_routes = tuple(ranked + ineligible)
    return AccountEmailRanking(
        classified_routes=all_routes,
        preferred_initial_route=preferred,
        alternative_routes=tuple(alternatives),
    )


def classify_account_email_routes(
    account: AccountInvestigation,
    *,
    named_person_safe: Callable[[ReachabilityRoute], bool] | None = None,
    allowed_classes: frozenset[EmailRouteClass] = DEFAULT_PILOT_ROUTE_CLASSES,
) -> AccountEmailRanking:
    """Classify and rank every email route on one account."""
    people = {c.candidate_id: c for c in account.candidates}
    classified: list[ClassifiedEmailRoute] = []
    for route in account.routes:
        if not is_email_channel(route):
            continue
        person = people.get(route.decision_unit_candidate_id or "")
        safe = False
        if named_person_safe is not None:
            safe = bool(named_person_safe(route))
        classified.append(
            evaluate_controlled_email_eligible(
                route,
                person=person,
                allowed_classes=allowed_classes,
                named_person_safe=safe,
            )
        )
    return rank_account_email_routes(classified)


def alternative_after_preferred_bounce(
    ranking: AccountEmailRanking,
    *,
    bounced_mailbox: str,
) -> ClassifiedEmailRoute | None:
    """Next eligible alternative when the preferred mailbox hard-bounced.

    Non-reply must not call this. Bounce of one mailbox does not kill the account.
    """
    bounced = (bounced_mailbox or "").strip().lower()
    remaining = [
        r
        for r in ranking.classified_routes
        if r.controlled_email_eligible and r.mailbox != bounced and r.suppression_state == SuppressionState.NONE.value
    ]
    remaining = sorted(remaining, key=_sort_key)
    return remaining[0] if remaining else None
