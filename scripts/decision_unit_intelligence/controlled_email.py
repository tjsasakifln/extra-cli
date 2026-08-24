"""Controlled email eligibility by route class.

Identity quality (`EMAIL_VALIDATED`, named-person evidence) stays a separate
signal from transport eligibility. ROLE / GENERIC / PUBLIC_COMPANY_FREEMAIL
may be controlled-eligible without a fabricated person and without promotion
to EMAIL_VALIDATED. PROBABILISTIC_OR_RISKY stays out of the default policy.

This module never grants auto-send.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from scripts.confenge_contact_resolution.mailbox_purpose import (
    CONTROLLED_BLOCKED_PURPOSES,
    classify_mailbox_purpose,
)
from scripts.decision_unit_intelligence.email_resolution import is_third_party_professional_domain
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelType,
    DecisionUnitCandidate,
    EpistemicClass,
    FreshnessState,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
)
from scripts.decision_unit_intelligence.reachability import (
    email_domain,
    is_brand_mailbox,
    is_freemail,
    is_generic_mailbox,
    is_role_mailbox,
    looks_nominal_local,
)

MAX_DEPARTMENTAL_HYPOTHESES = 3
DEPARTMENTAL_HYPOTHESIS_LOCALS: tuple[str, ...] = (
    "licitacao",
    "comercial",
    "contratos",
    "engenharia",
    "contato",
)

CONTROLLED_EMAIL_POLICY_VERSION = "controlled-email-policy.v1"
CONTROLLED_EMAIL_SCHEMA_VERSION = "confenge.outreach.controlled_email.v1"

# Tokens that genuinely mean "not suppressed". Anything else is treated as
# suppression, because an unknown token is not evidence of a clear mailbox.
CLEAR_SUPPRESSION_TOKENS = frozenset({"NONE", "CLEAR", "OK", "ACTIVE", "NOT_SUPPRESSED", "FALSE", "NO", "0"})

# Producers spell suppression in more than one vocabulary. Reading only two of
# these field names let an opted-out mailbox into a bounded pilot.
# Fields whose whole purpose is suppression. An unrecognized token here is not
# evidence of a clear mailbox, so it fails closed.
SUPPRESSION_TEXT_FIELDS = (
    "route_suppression",
    "suppression_state",
    "suppression",
    "suppression_reason",
)
# Fields that merely *may* carry a suppression word. `status` is deliberately
# not read at all: this repo uses it for READY, idle, backpressure and more, so
# failing closed on it would mark healthy contacts suppressed.
SUPPRESSION_HINT_FIELDS = ("email_status", "delivery_status", "contact_status")
SUPPRESSION_HINT_TOKENS = frozenset(
    {
        "UNSUBSCRIBED",
        "OPT_OUT",
        "OPTED_OUT",
        "COMPLAINED",
        "COMPLAINT",
        "SPAM",
        "BOUNCED",
        "HARD_BOUNCE",
        "SUPPRESSED",
        "BLOCKED",
        "BLOCKLISTED",
        "DNC",
        "DO_NOT_CONTACT",
    }
)
SUPPRESSION_FLAG_FIELDS = (
    "dnc",
    "do_not_contact",
    "unsubscribed",
    "opted_out",
    "suppressed",
    "is_suppressed",
    "complained",
    "spam_complaint",
    "blocklisted",
)
_FALSEY_TOKENS = frozenset({"", "0", "FALSE", "NO", "NONE", "NULL", "N"})

EVIDENCE_OBSERVED = "OBSERVED"
EVIDENCE_UNKNOWN = "UNKNOWN"

# `official_documents` is listed here so a mailbox on the account's own proven
# domain is accepted when it is found in a company-authored document. There is
# deliberately NO carve-out letting a document route skip the host/domain match:
# extraction cannot say which company a mailbox printed in a document belongs to.
# The document's CNPJ tag is the CNPJ that was queried, and the company name is
# supplied by the producer, so neither can bind the mailbox. Without a proven
# official domain, a document route has no association evidence at all.
COMPANY_ASSOCIATION_SOURCES = frozenset(
    {
        "company_website",
        "company_site",
        "official_documents",
        "official_document",
        "company_registry",
        "site",
        "institutional_site",
        "contact_page",
    }
)

# Snippet / tracking URLs cannot prove mailbox↔company association.
UNTRUSTWORTHY_SOURCE_URL_MARKERS = (
    "unsubscribe",
    "list-unsubscribe",
    "multisend-unsubscribe",
    "mail.google.com",
    "googleusercontent.com",
)

# Parser/template leftovers are not corporate domains.
IMPLAUSIBLE_MAILBOX_TLDS = frozenset(
    {
        "replace",
        "phone",
        "js",
        "ts",
        "local",
        "localhost",
        "invalid",
        "example",
        "test",
    }
)
HTML_ENTITY_LOCAL_MARKERS = ("u003e", "u003c", "u0026", "&gt;", "&lt;", "&amp;")

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
    source_url: str | None
    evidence_ids: tuple[str, ...]
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
    mailbox_department: str | None = None
    ownership_status: str = OwnershipStatus.UNKNOWN.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_account_id": self.canonical_account_id,
            "mailbox": self.mailbox,
            "route_class": self.route_class.value,
            "provenance": self.provenance,
            "source": self.source,
            "source_url": self.source_url,
            "source_reference": self.source_url or (self.evidence_ids[0] if self.evidence_ids else None),
            "evidence_ids": list(self.evidence_ids),
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
            "mailbox_department": self.mailbox_department,
            "ownership_status": self.ownership_status,
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


def _url_host(url: str | None) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").lower().removeprefix("www.")


def _hosts_equivalent(left: str | None, right: str | None) -> bool:
    a = str(left or "").lower().removeprefix("www.").strip()
    b = str(right or "").lower().removeprefix("www.").strip()
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def untrustworthy_source_url(url: str | None) -> bool:
    raw = str(url or "").strip().lower()
    if not raw:
        return False
    host = _url_host(raw)
    if any(marker in raw for marker in UNTRUSTWORTHY_SOURCE_URL_MARKERS):
        return True
    if host.endswith("gmail.com") and "unsub" in raw:
        return True
    return False


def _official_domain(route: ReachabilityRoute) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    return str(extra.get("official_domain") or extra.get("canonical_domain") or "").lower().removeprefix("www.").strip()


def mailbox_host_plausible(domain: str | None) -> bool:
    """Reject parser-minted hosts such as model.phone.replace."""
    host = str(domain or "").lower().removeprefix("www.").strip()
    if not host or "." not in host:
        return False
    if any(marker in host for marker in ("model.phone", ".phone.", "undefined", "null")):
        return False
    labels = [part for part in host.split(".") if part]
    if len(labels) < 2:
        return False
    tld = labels[-1]
    if tld in IMPLAUSIBLE_MAILBOX_TLDS or not tld.isalpha() or len(tld) < 2:
        return False
    if any(not label.replace("-", "").isalnum() for label in labels):
        return False
    return True


def mailbox_local_implausible(mailbox: str | None) -> bool:
    local = str(mailbox or "").split("@", 1)[0].lower()
    if not local:
        return True
    if any(marker in local for marker in HTML_ENTITY_LOCAL_MARKERS):
        return True
    if local in {"undefined", "null", "none", "true", "false"}:
        return True
    return False


def association_provenance_trustworthy(route: ReachabilityRoute) -> bool:
    """True only when public provenance can bind the mailbox to this account."""
    if untrustworthy_source_url(route.source_url):
        return False
    if mailbox_local_implausible(route.channel_value):
        return False
    source = str(route.source_type or "").lower().strip()
    mailbox_dom = email_domain(route.channel_value)
    url_host = _url_host(route.source_url)
    official = _official_domain(route)
    freemail = is_freemail(route.channel_value)
    extra = route.extra if isinstance(route.extra, dict) else {}
    registry_cnpj = "".join(ch for ch in str(extra.get("registry_cnpj14") or "") if ch.isdigit())
    route_cnpj = "".join(ch for ch in str(route.company_entity_id or "") if ch.isdigit())
    exact_official_registry_link = (
        source == "company_registry"
        and str(extra.get("official_match_status") or "").upper() == "MATCHED"
        and str(extra.get("official_authority") or "").upper() == "RECEITA_FEDERAL"
        and bool(str(extra.get("official_release_id") or "").strip())
        and len(registry_cnpj) == 14
        and registry_cnpj == route_cnpj
    )
    # An exact CNPJ row in a versioned Receita Federal release is itself the
    # public mailbox↔company association. It is valid for corporate freemail as
    # well, but does not imply a named person or role.
    if exact_official_registry_link:
        return True
    if not freemail and not mailbox_host_plausible(mailbox_dom):
        return False
    on_official_page = bool(official and url_host and _hosts_equivalent(url_host, official))
    mailbox_on_official = bool(official and mailbox_dom and not freemail and _hosts_equivalent(mailbox_dom, official))
    if official:
        if not mailbox_host_plausible(official) and not freemail:
            return False
        if source in COMPANY_ASSOCIATION_SOURCES:
            if freemail:
                return on_official_page
            return mailbox_on_official or (on_official_page and _hosts_equivalent(mailbox_dom, url_host))
        if on_official_page:
            return mailbox_on_official or freemail
        return False
    # Empty official_domain cannot prove a freemail belongs to this company
    # (aggregators such as cnpja.com publish third-party addresses).
    if freemail:
        return False
    if not url_host or not mailbox_dom:
        return False
    if not _hosts_equivalent(mailbox_dom, url_host):
        return False
    return source in COMPANY_ASSOCIATION_SOURCES | {"", "unknown"}


def mailbox_company_evidence(route: ReachabilityRoute) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    if not association_provenance_trustworthy(route):
        return EVIDENCE_UNKNOWN
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
    url_host = _url_host(route.source_url)
    mailbox_dom = email_domain(route.channel_value)
    official = _official_domain(route)
    if (
        mailbox_dom
        and not is_freemail(route.channel_value)
        and (_hosts_equivalent(mailbox_dom, official) or _hosts_equivalent(mailbox_dom, url_host))
    ):
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


def _observed_person_name(route: ReachabilityRoute, person: DecisionUnitCandidate | None) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    if person and str(person.person_name or "").strip():
        return str(person.person_name).strip()
    return str(extra.get("observed_person_name") or "").strip()


def mailbox_person_evidence(route: ReachabilityRoute, person: DecisionUnitCandidate | None) -> str:
    extra = route.extra if isinstance(route.extra, dict) else {}
    explicit = str(extra.get("mailbox_person_evidence") or "").upper()
    if explicit in {EVIDENCE_OBSERVED, EVIDENCE_UNKNOWN}:
        return explicit
    name = _observed_person_name(route, person)
    if extra.get("identity_explicitly_associated") is True and name:
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
    domain = email_domain(value)
    if domain and is_third_party_professional_domain(domain):
        return EmailRouteClass.PROBABILISTIC_OR_RISKY
    if _impossible_domain(route):
        return EmailRouteClass.PROBABILISTIC_OR_RISKY

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

    if person_ev == EVIDENCE_OBSERVED and _observed_person_name(route, person):
        return EmailRouteClass.DIRECT_PERSON

    if looks_nominal_local(value) and person_ev != EVIDENCE_OBSERVED:
        return EmailRouteClass.PROBABILISTIC_OR_RISKY

    if company_ev == EVIDENCE_OBSERVED:
        return EmailRouteClass.GENERIC_COMPANY
    return EmailRouteClass.PROBABILISTIC_OR_RISKY


def _verification_blob(route: ReachabilityRoute) -> dict[str, Any]:
    extra = route.extra if isinstance(route.extra, dict) else {}
    blob = extra.get("email_verification")
    return blob if isinstance(blob, dict) else extra


def _impossible_domain(route: ReachabilityRoute) -> bool:
    blob = _verification_blob(route)
    dns = str(blob.get("dns") or "").upper()
    mx = str(blob.get("mx") or "").upper()
    reasons = {str(code).upper() for code in (blob.get("reason_codes") or ())}
    return dns == "NXDOMAIN" or mx == "NULL_MX" or "NXDOMAIN" in reasons or "NULL_MX_DECLINES_EMAIL" in reasons


def is_actionable_controlled_company_route(item: ClassifiedEmailRoute) -> bool:
    """Operational success: a control-eligible company route, not a named person."""
    if not item.controlled_email_eligible:
        return False
    return item.route_class in DEFAULT_PILOT_ROUTE_CLASSES


def discovery_should_stop_for_commercial_value(
    classified: list[ClassifiedEmailRoute],
    *,
    deepen: bool = False,
) -> bool:
    """Stop PERSON-family spend once a control-eligible company route exists."""
    if deepen:
        return False
    return any(is_actionable_controlled_company_route(item) for item in classified)


def observed_contact_is_controlled_eligible_company_route(
    contact: dict[str, Any],
    *,
    account_id: str = "",
    official_domain: str | None = None,
) -> bool:
    """Same gate as evaluate_controlled_email_eligible. Nominal/third-party are not success."""
    if contact.get("pattern_guessed_email") or contact.get("email_derivation") == "INFERRED":
        return False
    email = canonicalize_mailbox(str(contact.get("email") or contact.get("value") or ""))
    if not email or "@" not in email:
        return False
    if str(contact.get("channel_epistemic_class") or contact.get("epistemic_class") or "").upper() == "INFERRED":
        return False
    payload = dict(contact)
    payload["email"] = email
    domain = email_domain(email)
    official = (official_domain or "").lower().removeprefix("www.")
    source = str(payload.get("source") or payload.get("source_type") or "").lower()
    if not source:
        # Do not mint company_website for foreign/unproven mailboxes.
        payload["source"] = "company_website" if official and domain == official else "unknown"
        source = payload["source"]
    extra = dict(payload.get("extra") or {})
    if official:
        extra.setdefault("official_domain", official)
        payload["extra"] = extra
    if official and domain == official:
        payload.setdefault("ownership_status", OwnershipStatus.COMPANY_OWNED.value)
    elif official and is_freemail(email) and source in COMPANY_ASSOCIATION_SOURCES:
        payload.setdefault("ownership_status", OwnershipStatus.COMPANY_OWNED.value)
        extra = dict(payload.get("extra") or {})
        extra.setdefault("company_associated", True)
        extra.setdefault("mailbox_company_evidence", EVIDENCE_OBSERVED)
        payload["extra"] = extra
    route = route_from_feed_contact(payload, account_id=account_id or "observed-contact")
    return is_actionable_controlled_company_route(evaluate_controlled_email_eligible(route))


def observed_channels_have_controlled_eligible_route(channels: list[Any]) -> bool:
    """True when an observed public mailbox is already a control-eligible company route."""
    for channel in channels or []:
        extra = getattr(channel, "extra", None) or {}
        if isinstance(channel, dict):
            if observed_contact_is_controlled_eligible_company_route(channel):
                return True
            continue
        epistemic = getattr(channel, "epistemic_class", None)
        if epistemic == EpistemicClass.INFERRED:
            continue
        ownership = getattr(channel, "ownership", None)
        contact = {
            "email": getattr(channel, "channel_value", None),
            "name": getattr(channel, "person_name", None),
            "ownership_status": ownership.value if hasattr(ownership, "value") else ownership,
            "source": getattr(channel, "source_type", None),
            "source_url": getattr(channel, "source_url", None),
            "channel_epistemic_class": epistemic.value if hasattr(epistemic, "value") else epistemic,
            "extra": extra,
            "pattern_guessed_email": extra.get("pattern_guessed") or extra.get("pattern_guessed_email"),
        }
        if observed_contact_is_controlled_eligible_company_route(contact):
            return True
    return False


def departmental_hypothesis_mailboxes(
    *,
    domain: str,
    already: frozenset[str] | set[str] = frozenset(),
    icp: bool = True,
    trigger: bool = True,
    proven_business_domain: bool = True,
    has_observed_usable_route: bool = False,
    limit: int = MAX_DEPARTMENTAL_HYPOTHESES,
) -> tuple[str, ...]:
    """Optional RISKY hypotheses. Never OBSERVED. Never default-eligible."""
    if not icp or not trigger or not proven_business_domain or has_observed_usable_route:
        return ()
    host = (domain or "").lower().removeprefix("www.").strip()
    if not host or "." not in host:
        return ()
    existing = {canonicalize_mailbox(item) for item in already}
    out: list[str] = []
    for local in DEPARTMENTAL_HYPOTHESIS_LOCALS:
        mailbox = f"{local}@{host}"
        if mailbox in existing:
            continue
        out.append(mailbox)
        if len(out) >= max(1, min(limit, MAX_DEPARTMENTAL_HYPOTHESES)):
            break
    return tuple(out)


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
    if _impossible_domain(route):
        eligible = False
        reasons.append("impossible_domain")
        domain = email_domain(mailbox)
        blob = _verification_blob(route)
        if str(blob.get("dns") or "").upper() == "NXDOMAIN":
            reasons.append("nxdomain")
        if str(blob.get("mx") or "").upper() == "NULL_MX":
            reasons.append("null_mx")
        if domain and is_third_party_professional_domain(domain):
            reasons.append("third_party_professional_domain")
    domain = email_domain(mailbox)
    if domain and is_third_party_professional_domain(domain):
        eligible = False
        reasons.append("third_party_professional_domain")
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
    if mailbox_local_implausible(mailbox):
        eligible = False
        reasons.append("html_entity_or_template_local_part")
    domain = email_domain(mailbox)
    if domain and not is_freemail(mailbox) and not mailbox_host_plausible(domain):
        eligible = False
        reasons.append("implausible_mailbox_host")
    if company_ev != EVIDENCE_OBSERVED:
        eligible = False
        reasons.append("mailbox_company_evidence_unknown")
        if untrustworthy_source_url(route.source_url):
            reasons.append("untrustworthy_source_url")
        if not str(route.source_type or "").strip() and not str(route.source_url or "").strip():
            reasons.append("missing_provenance")
        if str(route.source_type or "").lower() == "web_search" and company_ev != EVIDENCE_OBSERVED:
            reasons.append("web_search_unassociated")
        url_host = _url_host(route.source_url)
        if domain and url_host and not _hosts_equivalent(domain, url_host):
            reasons.append("mailbox_source_host_mismatch")
    if route_class == EmailRouteClass.DIRECT_PERSON and person_ev != EVIDENCE_OBSERVED:
        eligible = False
        reasons.append("direct_person_requires_named_person_evidence")
    if route_class == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL and company_ev != EVIDENCE_OBSERVED:
        eligible = False
        reasons.append("freemail_requires_company_association")

    person_id = None
    person_name = None
    if route_class == EmailRouteClass.DIRECT_PERSON and person_ev == EVIDENCE_OBSERVED:
        person_name = _observed_person_name(route, person) or None
        extra_id = str(extra.get("observed_person_id") or "").strip()
        if person and person.person_id:
            person_id = person.person_id
        elif extra_id:
            person_id = extra_id
        if person_name:
            reasons.append("named_person_evidence_present")
        else:
            reasons.append("person_unknown")
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
        source_url=route.source_url,
        evidence_ids=tuple(route.evidence_ids),
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
        mailbox_department=route.target_role if department_ev == EVIDENCE_OBSERVED else None,
        ownership_status=route.ownership.value,
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
            source_url=item.source_url,
            evidence_ids=item.evidence_ids,
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
            mailbox_department=item.mailbox_department,
            ownership_status=item.ownership_status,
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


def _channel_for_mailbox(mailbox: str) -> ChannelType:
    if is_role_mailbox(mailbox):
        return ChannelType.ROLE_MAILBOX
    if is_generic_mailbox(mailbox) or is_brand_mailbox(mailbox) or is_freemail(mailbox):
        return ChannelType.GENERIC_CORPORATE_EMAIL
    return ChannelType.DIRECT_EMAIL


def _relation_for_mailbox(mailbox: str) -> RouteRelation:
    if is_role_mailbox(mailbox):
        return RouteRelation.ROUTES_TO_ROLE
    if looks_nominal_local(mailbox) and not is_generic_mailbox(mailbox):
        return RouteRelation.PERSON_OWNS_CHANNEL
    return RouteRelation.ACCOUNT_LEVEL_ONLY


def _feed_contact_source_type(contact: dict[str, Any]) -> str:
    prov = contact.get("provenance") if isinstance(contact.get("provenance"), dict) else {}
    return str(contact.get("source") or contact.get("source_type") or prov.get("source_type") or "").strip()


def _feed_contact_source_url(contact: dict[str, Any]) -> str:
    prov = contact.get("provenance") if isinstance(contact.get("provenance"), dict) else {}
    return str(contact.get("source_url") or prov.get("source_url") or "").strip()


def _suppression_flag(value: Any) -> bool:
    """Truthiness for a producer flag, without letting the string "false" suppress.

    A producer that emits string booleans would otherwise starve the whole
    cohort, and one that emits 1 / "yes" would otherwise slip past an identity
    comparison against True.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().upper() not in _FALSEY_TOKENS
    return bool(value)


def _suppression_sources(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """The contact plus the nested shapes this schema already uses elsewhere."""
    out = [contact]
    for key in ("provenance", "extra"):
        nested = contact.get(key)
        if isinstance(nested, dict):
            out.append(nested)
    return out


def suppression_from_feed_contact(contact: dict[str, Any]) -> SuppressionState:
    """Read suppression fail-closed across every shape a producer may use."""
    state = SuppressionState.NONE
    for source in _suppression_sources(contact):
        for field in SUPPRESSION_TEXT_FIELDS:
            raw = source.get(field)
            if raw is None or isinstance(raw, bool):
                continue
            token = str(raw).upper().replace("-", "_").strip()
            if not token or token in CLEAR_SUPPRESSION_TOKENS:
                continue
            if token in {s.value for s in SuppressionState}:
                return SuppressionState(token)
            # An unrecognized token is not evidence of a clear mailbox.
            state = SuppressionState.BLOCKED
        for field in SUPPRESSION_HINT_FIELDS:
            raw = source.get(field)
            if raw is None or isinstance(raw, bool):
                continue
            token = str(raw).upper().replace("-", "_").strip()
            if token in {s.value for s in SuppressionState} and token not in CLEAR_SUPPRESSION_TOKENS:
                return SuppressionState(token)
            if token in SUPPRESSION_HINT_TOKENS:
                return SuppressionState.DNC
        for field in SUPPRESSION_FLAG_FIELDS:
            if field in source and _suppression_flag(source.get(field)):
                return SuppressionState.DNC
        if "opt_out" in source and _suppression_flag(source.get("opt_out")):
            return SuppressionState.OPT_OUT
        for field in ("bounce", "bounced", "hard_bounce"):
            if field in source and _suppression_flag(source.get(field)):
                return SuppressionState.HARD_BOUNCE
    return state


def route_from_feed_contact(
    contact: dict[str, Any],
    *,
    account_id: str,
    official_domain: str | None = None,
) -> ReachabilityRoute:
    """Build a ReachabilityRoute from an outreach contact dict. Does not mint people."""
    mailbox = str(contact.get("email") or contact.get("channel_value") or "").strip().lower()
    extra = dict(contact.get("extra") or {})
    host = str(official_domain or extra.get("official_domain") or "").lower().removeprefix("www.").strip()
    if host:
        extra.setdefault("official_domain", host)
    # Ownership is not proof. Never mint OBSERVED association from the flag alone.
    if contact.get("ownership_status") == OwnershipStatus.COMPANY_OWNED.value:
        extra.setdefault("company_associated", True)
    if contact.get("mailbox_company_evidence"):
        extra["mailbox_company_evidence"] = str(contact["mailbox_company_evidence"])
    if contact.get("identity_explicitly_associated") is True or (
        contact.get("name_explicitly_published") is True and contact.get("email_explicitly_published") is True
    ):
        extra.setdefault("identity_explicitly_associated", True)
    observed_name = str(contact.get("name") or contact.get("person_name") or "").strip()
    if observed_name:
        extra.setdefault("observed_person_name", observed_name)
    observed_id = str(contact.get("person_id") or "").strip()
    if observed_id:
        extra.setdefault("observed_person_id", observed_id)
    evidence_strength = str(contact.get("evidence_strength") or "").strip().lower()
    if evidence_strength:
        extra.setdefault("evidence_strength", evidence_strength)
    document_cnpj = re.sub(
        r"\D",
        "",
        str(contact.get("document_cnpj14") or contact.get("cnpj14") or contact.get("cnpj") or ""),
    )[:14]
    if len(document_cnpj) == 14:
        extra.setdefault("document_cnpj14", document_cnpj)
    if contact.get("pattern_guessed_email") or contact.get("pattern_guessed"):
        extra.setdefault("pattern_guessed_email", True)
    discovery = contact.get("email_discovery_class") or contact.get("route_class")
    if discovery:
        extra.setdefault("email_discovery_class", str(discovery))
    suppression = suppression_from_feed_contact(contact)
    ownership = OwnershipStatus.UNKNOWN
    raw_own = str(contact.get("ownership_status") or "").upper()
    if raw_own in {o.value for o in OwnershipStatus}:
        ownership = OwnershipStatus(raw_own)
    epistemic = EpistemicClass.OBSERVED
    if str(contact.get("channel_epistemic_class") or contact.get("epistemic_class") or "").upper() == "INFERRED":
        epistemic = EpistemicClass.INFERRED
    if str(contact.get("email_derivation") or "").upper() == "INFERRED":
        epistemic = EpistemicClass.INFERRED
    raw_freshness = str(contact.get("route_freshness") or contact.get("freshness") or "").upper()
    freshness = (
        FreshnessState(raw_freshness)
        if raw_freshness in {item.value for item in FreshnessState}
        else FreshnessState.FRESH
    )
    evidence_ids = [str(item) for item in (contact.get("evidence_ids") or []) if item]
    return ReachabilityRoute(
        route_id=str(contact.get("source_contact_id") or contact.get("route_id") or mailbox),
        company_entity_id=account_id,
        channel_type=_channel_for_mailbox(mailbox),
        reachability_class=ReachabilityClass.R5_CORPORATE_ONLY,
        action_mode=ActionMode.GENERIC_EMAIL_LAST_RESORT,
        target_role=str(contact.get("mailbox_department") or "").strip() or None,
        channel_value=mailbox,
        route_relation=_relation_for_mailbox(mailbox),
        epistemic_class=epistemic,
        source_type=_feed_contact_source_type(contact),
        source_url=_feed_contact_source_url(contact) or None,
        evidence_ids=evidence_ids,
        freshness=freshness,
        ownership=ownership,
        suppression=suppression,
        observed_at=str(contact.get("observed_at") or contact.get("source_date") or "") or None,
        extra=extra,
    )


def canonicalize_mailbox(email: str | None) -> str:
    return str(email or "").strip().lower()


def apply_preferred_recommended_alias(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`recommended` is a compatibility alias of the unique preferred_initial principal.

    Historical Warmbly/v1 consumers read `recommended=true` as the single principal
    recipient. The canonical field is now `preferred_initial`. They must agree.
    A preferred generic/role mailbox may be recommended even when it is not
    `email_send_ready` (named-person EMAIL_VALIDATED).
    """
    stamped: list[dict[str, Any]] = []
    for contact in contacts:
        if not isinstance(contact, dict):
            stamped.append(contact)
            continue
        updated = dict(contact)
        updated["recommended"] = bool(updated.get("preferred_initial"))
        stamped.append(updated)
    return stamped


def _merge_feed_contact(primary: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Keep one mailbox row; secondary sources become corroboration, not rivals."""
    merged = dict(primary)
    sources: list[str] = list(merged.get("corroborating_sources") or [])
    for key in ("source_url", "source", "source_document"):
        value = extra.get(key)
        if value and str(value) not in sources and str(value) != str(merged.get(key) or ""):
            sources.append(str(value))
    if extra.get("source_url") and not merged.get("source_url"):
        merged["source_url"] = extra["source_url"]
    if sources:
        merged["corroborating_sources"] = sources
        merged["corroborated"] = True
    for flag in (
        "email_explicitly_published",
        "name_explicitly_published",
        "role_explicitly_published",
        "human_identity_evidence_valid",
        "identity_explicitly_associated",
    ):
        if extra.get(flag) and not merged.get(flag):
            merged[flag] = extra[flag]
    if extra.get("name") and not merged.get("name"):
        merged["name"] = extra["name"]
    if extra.get("person_id") and not merged.get("person_id"):
        merged["person_id"] = extra["person_id"]
    return merged


def dedupe_feed_contacts_by_mailbox(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonicalize mailboxes. One row per address; later sources corroborate."""
    order: list[str] = []
    by_mailbox: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        email = canonicalize_mailbox(str(contact.get("email") or ""))
        if not email or "@" not in email:
            passthrough.append(contact)
            continue
        if email in by_mailbox:
            by_mailbox[email] = _merge_feed_contact(by_mailbox[email], contact)
            continue
        order.append(email)
        by_mailbox[email] = dict(contact)
        by_mailbox[email]["email"] = email
    return [by_mailbox[email] for email in order] + passthrough


def feed_contact_from_classified(item: ClassifiedEmailRoute) -> dict[str, Any]:
    """Shape one classified route as a confenge.outreach.v1 contact for Warmbly ingest."""
    person_unknown = item.person_id is None and not item.person_name
    out: dict[str, Any] = {
        "source_contact_id": item.route_id or item.mailbox,
        "email": item.mailbox,
        "route_class": item.route_class.value,
        "provenance_class": item.provenance,
        "evidence_ids": list(item.evidence_ids),
        "controlled_email_eligible": item.controlled_email_eligible,
        "preferred_initial": item.preferred_initial,
        "recommended": item.preferred_initial,
        "preferred_rank": item.preferred_rank,
        "mailbox_company_evidence": item.mailbox_company_evidence,
        "mailbox_person_evidence": item.mailbox_person_evidence,
        "mailbox_department_evidence": item.mailbox_department_evidence,
        "person_unknown": person_unknown,
        "email_validated": item.email_validated,
        "risk_class": item.risk_class.value,
        "channel_epistemic_class": item.epistemic_class,
        "route_freshness": item.freshness,
        "route_suppression": item.suppression_state,
        "ownership_status": item.ownership_status,
        "policy_version": item.policy_version,
        "schema_version": item.schema_version,
        "reason_codes": list(item.reason_codes),
    }
    source_reference = item.source_url or (item.evidence_ids[0] if item.evidence_ids else None)
    if item.source:
        out["source"] = item.source
    if item.source_url:
        out["source_url"] = item.source_url
    if source_reference:
        out["source_reference"] = source_reference
    if item.observed_at:
        out["observed_at"] = item.observed_at
    if item.mailbox_department:
        out["mailbox_department"] = item.mailbox_department
    if item.source or item.source_url or item.evidence_ids or item.observed_at:
        provenance: dict[str, Any] = {"epistemic_class": item.provenance}
        if item.source:
            provenance["source_type"] = item.source
        if item.source_url:
            provenance["source_url"] = item.source_url
        if item.observed_at:
            provenance["observed_at"] = item.observed_at
        if item.evidence_ids:
            provenance["evidence_ids"] = list(item.evidence_ids)
        out["provenance"] = provenance
    if item.person_name:
        out["name"] = item.person_name
    if item.person_id:
        out["person_id"] = item.person_id
    return out


def stamp_and_rank_feed_contacts(
    contacts: list[dict[str, Any]],
    *,
    account_id: str,
    official_domain: str | None = None,
) -> list[dict[str, Any]]:
    """Stamp route_class + controlled_email_eligible on ingestible contacts[]."""
    unique = dedupe_feed_contacts_by_mailbox(contacts)
    classified: list[ClassifiedEmailRoute] = []
    indexed: list[dict[str, Any]] = []
    for contact in unique:
        if not isinstance(contact, dict):
            continue
        email = canonicalize_mailbox(str(contact.get("email") or ""))
        if not email or "@" not in email:
            indexed.append(contact)
            continue
        route = route_from_feed_contact(contact, account_id=account_id, official_domain=official_domain)
        item = evaluate_controlled_email_eligible(route, person=None)
        classified.append(item)
        indexed.append(contact)
    ranking = rank_account_email_routes(classified)
    by_mailbox = {item.mailbox: item for item in ranking.classified_routes}
    stamped: list[dict[str, Any]] = []
    for contact in indexed:
        email = canonicalize_mailbox(str(contact.get("email") or ""))
        item = by_mailbox.get(email)
        if item is None:
            stamped.append(contact)
            continue
        classified_contact = feed_contact_from_classified(item)
        original_provenance = contact.get("provenance")
        classified_provenance = classified_contact.get("provenance")
        merged = {**contact, **classified_contact}
        if isinstance(original_provenance, dict) and isinstance(classified_provenance, dict):
            merged["provenance"] = {**original_provenance, **classified_provenance}
        if contact.get("corroborating_sources"):
            merged["corroborating_sources"] = list(contact["corroborating_sources"])
            merged["corroborated"] = True
        stamped.append(merged)
    return apply_preferred_recommended_alias(stamped)


def _shared_mailbox_owner(leads: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Pick the one account that keeps each shared mailbox, stably across runs.

    Feed order is sorted by target-fit freshness timestamps, which advance on
    every refresh, so "first lead wins" silently moved a shared mailbox between
    accounts — and dropped last run's account out of the pilot — with no change
    in mailbox evidence. Decide on the account id instead.
    """
    owner: dict[str, str] = {}
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        account = str(company.get("cnpj14") or lead.get("source_lead_id") or "")
        if not account:
            continue
        for contact in lead.get("contacts") or []:
            if not isinstance(contact, dict) or not contact.get("preferred_initial"):
                continue
            mailbox = canonicalize_mailbox(str(contact.get("email") or ""))
            if not mailbox:
                continue
            current = owner.get(mailbox)
            if current is None or account < current:
                owner[mailbox] = account
    return owner


def shared_preferred_mailbox_owner(leads: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Public whole-feed view of who keeps each shared mailbox."""
    return _shared_mailbox_owner(leads)


def apply_cross_account_preferred_mailbox_gate(
    leads: list[dict[str, Any]],
    *,
    owner: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Exactly one account may keep a preferred mailbox. Other claimants lose it.

    ``owner`` carries a whole-feed decision computed elsewhere, so a streaming
    caller can apply the gate one lead at a time without holding the feed.
    """
    claimed: dict[str, str] = dict(owner if owner is not None else _shared_mailbox_owner(leads))
    out: list[dict[str, Any]] = []
    for lead in leads:
        if not isinstance(lead, dict):
            out.append(lead)
            continue
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        account = str(company.get("cnpj14") or lead.get("source_lead_id") or "")
        updated_contacts: list[Any] = []
        for contact in lead.get("contacts") or []:
            if not isinstance(contact, dict):
                updated_contacts.append(contact)
                continue
            item = dict(contact)
            mailbox = canonicalize_mailbox(str(item.get("email") or ""))
            if item.get("preferred_initial") and mailbox:
                owner = claimed.get(mailbox)
                if owner is not None and owner != account:
                    item["preferred_initial"] = False
                    item["recommended"] = False
                    item["controlled_email_eligible"] = False
                    item["reason_codes"] = list(item.get("reason_codes") or []) + [
                        "duplicate_preferred_mailbox_across_accounts"
                    ]
                else:
                    claimed[mailbox] = account
            updated_contacts.append(item)
        refreshed = dict(lead)
        refreshed["contacts"] = updated_contacts
        out.append(refreshed)
    return out
