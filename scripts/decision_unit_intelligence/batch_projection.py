"""Verified derived projection from durable discovery jobs into bridge contacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_target_fit.company_key import canonical_target_membership
from scripts.decision_unit_intelligence.batch_contact_metadata import attach_projection_evidence
from scripts.decision_unit_intelligence.batch_queue import ContactDiscoveryQueue, canonical_payload_hash
from scripts.decision_unit_intelligence.controlled_email import (
    CONTROLLED_EMAIL_POLICY_VERSION,
    apply_cross_account_preferred_mailbox_gate,
    classify_account_email_routes,
    feed_contact_from_classified,
    stamp_and_rank_feed_contacts,
)
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelType,
    ConfidenceLevel,
    DecisionRoleClass,
    DecisionUnitCandidate,
    EpistemicClass,
    FreshnessState,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
)
from scripts.decision_unit_intelligence.projection import is_email_safe_for_warmbly
from scripts.decision_unit_intelligence.repository import write_json

TERMINAL_JOB_STATUSES = frozenset({"SUCCEEDED", "BLOCKED", "DLQ", "CANCELLED"})
ENRICHMENT_TERMINALS = frozenset({"EMAIL_ROUTE_READY", "NO_PUBLIC_EMAIL_FOUND", "BLOCKED_WITH_REASON"})

_CLEAR_SUPPRESSION = frozenset({"", "NONE", "CLEAR", "NOT_SUPPRESSED"})
_OFFICIAL_ASSOCIATION_FIELDS = (
    "official_match_status",
    "official_authority",
    "official_release_id",
    "registry_cnpj14",
    "source_provenance",
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_verified_output(job: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    pointer = str(job.get("output_pointer") or "").strip()
    expected = str(job.get("output_hash") or "").strip()
    if not pointer:
        return None, "OUTPUT_POINTER_MISSING"
    if not expected:
        return None, "OUTPUT_HASH_MISSING"
    path = Path(pointer)
    if not path.is_file():
        return None, "OUTPUT_FILE_MISSING"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "OUTPUT_UNREADABLE"
    if not isinstance(payload, dict):
        return None, "OUTPUT_NOT_OBJECT"
    if expected and canonical_payload_hash(payload) != expected:
        return None, "OUTPUT_HASH_MISMATCH"
    if int(payload.get("job_id") or -1) != int(job["id"]):
        return None, "OUTPUT_JOB_ID_MISMATCH"
    if str(payload.get("canonical_account_id") or "") != str(job["canonical_account_id"]):
        return None, "OUTPUT_ACCOUNT_MISMATCH"
    return payload, None


def _blocked_row(job: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "cnpj14": str(job["canonical_account_id"]),
        "canonical_account_id": str(job["canonical_account_id"]),
        "contacts": [],
        "enrichment_state": "BLOCKED_WITH_REASON",
        "enrichment_reason": reason,
        "contact_discovery_job_id": int(job["id"]),
        "contact_discovery_output_hash": job.get("output_hash"),
    }


def _canonical_mailbox(contact: dict[str, Any]) -> str:
    return str(contact.get("email") or contact.get("mailbox") or "").strip().lower()


def _contact_observed_at(contact: dict[str, Any]) -> str:
    """Return the public observation timestamp carried by one route."""
    direct = str(contact.get("observed_at") or "").strip()
    if direct:
        return direct
    for field in ("provenance", "source_provenance"):
        nested = contact.get(field)
        if isinstance(nested, dict):
            observed = str(nested.get("observed_at") or "").strip()
            if observed:
                return observed
    return ""


def _has_official_match(contact: dict[str, Any], account_id: str) -> bool:
    """Verify the complete immutable registry tuple for this exact CNPJ."""
    provenance = contact.get("source_provenance")
    release_id = str(contact.get("official_release_id") or "").strip()
    registry_cnpj = "".join(char for char in str(contact.get("registry_cnpj14") or "") if char.isdigit())
    account_cnpj = "".join(char for char in str(account_id or "") if char.isdigit())
    return bool(
        str(contact.get("official_match_status") or "").upper() == "MATCHED"
        and str(contact.get("official_authority") or "").upper() == "RECEITA_FEDERAL"
        and str(contact.get("source") or contact.get("source_type") or "").lower() in {"company_registry", "registry"}
        and len(registry_cnpj) == 14
        and registry_cnpj == account_cnpj
        and release_id
        and isinstance(provenance, dict)
        and str(provenance.get("release_id") or "").strip() == release_id
        and _contact_observed_at(contact)
    )


def _merge_contact_evidence(
    prior: dict[str, Any],
    current: dict[str, Any],
    *,
    account_id: str,
) -> dict[str, Any]:
    """Union the same observed mailbox without allowing evidence regression.

    Current facts win generally, but a later provider failure or an older
    serializer cannot erase an exact official CNPJ association.  Suppression is
    fail-closed: a known non-clear state from either observation survives.
    Eligibility/rank fields are derived again after the factual union.
    """
    merged = {**prior, **current}
    prior_exact = _has_official_match(prior, account_id)
    current_exact = _has_official_match(current, account_id)
    if prior_exact and not current_exact:
        for field in (
            *_OFFICIAL_ASSOCIATION_FIELDS,
            "source_reference",
            "source_url",
            "observed_at",
        ):
            if prior.get(field) is not None:
                value = prior[field]
                merged[field] = dict(value) if isinstance(value, dict) else value
    if prior_exact or current_exact:
        # These are derived from the complete immutable official tuple above,
        # not trusted merely because an older serializer emitted them.
        merged["company_associated"] = True
        merged["mailbox_company_evidence"] = "OBSERVED"
        merged["ownership_status"] = "COMPANY_OWNED"

    evidence_ids = [
        str(item) for item in [*(prior.get("evidence_ids") or []), *(current.get("evidence_ids") or [])] if item
    ]
    if evidence_ids:
        merged["evidence_ids"] = list(dict.fromkeys(evidence_ids))

    for field in ("route_suppression", "suppression_state", "suppression"):
        values = [str(source.get(field) or "").upper() for source in (current, prior)]
        suppressing = next((value for value in values if value not in _CLEAR_SUPPRESSION), None)
        if suppressing:
            merged[field] = suppressing

    merged["email"] = _canonical_mailbox(current) or _canonical_mailbox(prior)
    return merged


def _merge_account_contacts(
    prior_contacts: list[dict[str, Any]],
    current_contacts: list[dict[str, Any]],
    *,
    account_id: str,
) -> list[dict[str, Any]]:
    by_mailbox: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for contact in prior_contacts:
        mailbox = _canonical_mailbox(contact)
        if not mailbox or "@" not in mailbox:
            continue
        if mailbox not in by_mailbox:
            order.append(mailbox)
            by_mailbox[mailbox] = dict(contact)
    for contact in current_contacts:
        mailbox = _canonical_mailbox(contact)
        if not mailbox or "@" not in mailbox:
            continue
        if mailbox not in by_mailbox:
            order.append(mailbox)
            by_mailbox[mailbox] = dict(contact)
        else:
            by_mailbox[mailbox] = _merge_contact_evidence(
                by_mailbox[mailbox],
                contact,
                account_id=account_id,
            )
    return [by_mailbox[mailbox] for mailbox in order]


def _rank_publishable_contacts(
    contacts: list[dict[str, Any]],
    *,
    account_id: str,
    official_domain: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Rank routes while refusing an eligible route with no observation time.

    Discovery evidence remains stored as an alternative, but the publication
    contract cannot call it ready or preferred without the timestamp needed to
    assess freshness.  This guard lives at the durable projection boundary so
    historical serializers cannot bypass it by replaying stale derived flags.
    """
    stamped = stamp_and_rank_feed_contacts(
        contacts,
        account_id=account_id,
        official_domain=official_domain,
    )
    rejected_mailboxes = {
        _canonical_mailbox(contact)
        for contact in stamped
        if not _contact_observed_at(contact)
        and "controlled_email_eligible" in (contact.get("reason_codes") or [])
        and "missing_observed_at" in (contact.get("reason_codes") or [])
    }
    rejected_mailboxes.discard("")
    if not rejected_mailboxes:
        return stamped, 0

    reranked = stamp_and_rank_feed_contacts(
        [contact for contact in stamped if _canonical_mailbox(contact) not in rejected_mailboxes],
        account_id=account_id,
        official_domain=official_domain,
    )
    valid_by_mailbox = {_canonical_mailbox(contact): contact for contact in reranked}
    guarded: list[dict[str, Any]] = []
    for contact in stamped:
        mailbox = _canonical_mailbox(contact)
        if mailbox not in rejected_mailboxes:
            guarded.append(valid_by_mailbox.get(mailbox, contact))
            continue
        demoted = dict(contact)
        reasons = [str(item) for item in (demoted.get("reason_codes") or []) if item]
        reasons.extend(("missing_observed_at", "publication_contract_rejected"))
        demoted.update(
            {
                "controlled_email_eligible": False,
                "preferred_initial": False,
                "recommended": False,
                "preferred_rank": None,
                "risk_class": "RISKY",
                "publication_block_reason": "MISSING_OBSERVED_AT",
                "reason_codes": list(dict.fromkeys(reasons)),
            }
        )
        guarded.append(demoted)
    return guarded, len(rejected_mailboxes)


def _preferred_route_from_contact(account_id: str, contact: dict[str, Any]) -> dict[str, Any]:
    route = dict(contact)
    route["canonical_account_id"] = account_id
    route["mailbox"] = _canonical_mailbox(contact)
    # Keep the preferred-route contract stable when the publication guard has
    # to rebuild it from the ingestible contact row.  Feed contacts use `name`,
    # while the controlled route contract deliberately uses `person_name` and
    # represents an unknown person as an explicit null.
    route.setdefault("person_id", contact.get("person_id"))
    route.setdefault("person_name", contact.get("name"))
    route.setdefault("epistemic_class", contact.get("channel_epistemic_class"))
    route.setdefault("freshness", contact.get("route_freshness"))
    route.setdefault("suppression_state", contact.get("route_suppression"))
    return route


def reconcile_prior_contact_rows(
    current_rows: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Reconcile the latest full cohort with prior durable public evidence.

    The latest cohort remains the denominator.  Prior rows can restore evidence
    for the same account/mailbox, but can never add an account that the current
    TARGET_CONFIRMED population did not process.
    """
    prior_by_account = {
        str(row.get("canonical_account_id") or row.get("cnpj14") or ""): row
        for row in prior_rows
        if str(row.get("canonical_account_id") or row.get("cnpj14") or "")
    }
    before_preferred = sum(bool(row.get("preferred_email_route")) for row in current_rows)
    recovered_from_prior = 0
    reconciled: list[dict[str, Any]] = []
    for raw in current_rows:
        row = dict(raw)
        account_id = str(row.get("canonical_account_id") or row.get("cnpj14") or "")
        prior = prior_by_account.get(account_id) or {}
        current_contacts = [dict(item) for item in (row.get("contacts") or []) if isinstance(item, dict)]
        prior_contacts = [dict(item) for item in (prior.get("contacts") or []) if isinstance(item, dict)]
        combined = _merge_account_contacts(
            prior_contacts,
            current_contacts,
            account_id=account_id,
        )
        official_domain = str(row.get("official_domain") or prior.get("official_domain") or "").strip()
        stamped, rejected_missing_observed_at = _rank_publishable_contacts(
            combined,
            account_id=account_id,
            official_domain=official_domain or None,
        )
        preferred_contact = next(
            (item for item in stamped if item.get("preferred_initial") and item.get("controlled_email_eligible")),
            None,
        )
        latest_state = str(row.get("enrichment_state") or "")
        latest_reason = str(row.get("enrichment_reason") or "")
        row["contacts"] = stamped
        row["official_domain"] = official_domain or None
        row["latest_enrichment_state"] = latest_state
        row["latest_enrichment_reason"] = latest_reason
        if rejected_missing_observed_at:
            row["publication_guard_failures"] = {
                "MISSING_OBSERVED_AT": rejected_missing_observed_at,
            }
        else:
            row.pop("publication_guard_failures", None)
        if preferred_contact is not None:
            row["preferred_email_route"] = _preferred_route_from_contact(account_id, preferred_contact)
            row["enrichment_state"] = "EMAIL_ROUTE_READY"
            row["enrichment_reason"] = "DURABLE_EVIDENCE_ROUTE_SELECTED"
            if not raw.get("preferred_email_route"):
                recovered_from_prior += 1
        else:
            row.pop("preferred_email_route", None)
            if latest_state == "EMAIL_ROUTE_READY":
                row["enrichment_state"] = "BLOCKED_WITH_REASON"
                row["enrichment_reason"] = (
                    "CONTACT_ROUTE_MISSING_OBSERVED_AT"
                    if rejected_missing_observed_at
                    else "CURRENT_POLICY_NO_ELIGIBLE_ROUTE"
                )
        reconciled.append(row)
    after_preferred = sum(bool(row.get("preferred_email_route")) for row in reconciled)
    return reconciled, {
        "prior_accounts": len(prior_by_account),
        "current_accounts": len(current_rows),
        "accounts_in_both": sum(
            str(row.get("canonical_account_id") or row.get("cnpj14") or "") in prior_by_account for row in current_rows
        ),
        "preferred_before_reconciliation": before_preferred,
        "preferred_after_reconciliation": after_preferred,
        "preferred_recovered_from_prior": recovered_from_prior,
        "routes_rejected_missing_observed_at": sum(
            int((row.get("publication_guard_failures") or {}).get("MISSING_OBSERVED_AT") or 0) for row in reconciled
        ),
    }


_IDENTITY_GUARD_BLOCKERS = (
    (
        "shared_mailbox_without_account_identity_evidence",
        "CONTACT_SHARED_MAILBOX_WITHOUT_ACCOUNT_IDENTITY_EVIDENCE",
    ),
    (
        "duplicate_preferred_mailbox_across_accounts",
        "CONTACT_DUPLICATE_PREFERRED_MAILBOX_ACROSS_ACCOUNTS",
    ),
    (
        "recipient_without_account_identity_evidence",
        "CONTACT_RECIPIENT_WITHOUT_ACCOUNT_IDENTITY_EVIDENCE",
    ),
)
_IDENTITY_GUARD_REASON_CODES = frozenset(reason for reason, _ in _IDENTITY_GUARD_BLOCKERS)


def apply_authoritative_identity_gate(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Make the durable terminal ledger match the authoritative feed policy."""

    policy_input = [
        {
            "source_lead_id": str(row.get("canonical_account_id") or row.get("cnpj14") or ""),
            "company": {
                "cnpj14": str(row.get("canonical_account_id") or row.get("cnpj14") or ""),
            },
            "contacts": row.get("contacts") or [],
        }
        for row in rows
    ]
    gated = apply_cross_account_preferred_mailbox_gate(
        policy_input,
        require_account_identity_evidence=True,
    )
    preferred_before = sum(bool(row.get("preferred_email_route")) for row in rows)
    rejected_routes: Counter[str] = Counter()
    accounts_demoted = 0
    out: list[dict[str, Any]] = []
    for raw, policy_row in zip(rows, gated, strict=True):
        row = dict(raw)
        contacts = [dict(item) for item in (policy_row.get("contacts") or []) if isinstance(item, dict)]
        row["contacts"] = contacts
        preferred = next(
            (
                item
                for item in contacts
                if item.get("preferred_initial") and item.get("controlled_email_eligible")
            ),
            None,
        )
        guard_counts = Counter(
            reason
            for contact in contacts
            for reason in (contact.get("reason_codes") or [])
            if reason in _IDENTITY_GUARD_REASON_CODES
        )
        failures = dict(row.get("publication_guard_failures") or {})
        for reason, count in guard_counts.items():
            failures[reason.upper()] = int(count)
            rejected_routes[reason] += int(count)
        if failures:
            row["publication_guard_failures"] = failures
        else:
            row.pop("publication_guard_failures", None)

        if preferred is not None:
            account_id = str(row.get("canonical_account_id") or row.get("cnpj14") or "")
            row["preferred_email_route"] = _preferred_route_from_contact(account_id, preferred)
            row["enrichment_state"] = "EMAIL_ROUTE_READY"
            row["enrichment_reason"] = "AUTHORITATIVE_IDENTITY_ROUTE_SELECTED"
        else:
            had_preferred = bool(row.pop("preferred_email_route", None))
            if had_preferred or row.get("enrichment_state") == "EMAIL_ROUTE_READY":
                accounts_demoted += 1
                row["enrichment_state"] = "BLOCKED_WITH_REASON"
                row["enrichment_reason"] = next(
                    (
                        blocker
                        for reason, blocker in _IDENTITY_GUARD_BLOCKERS
                        if guard_counts.get(reason)
                    ),
                    "CURRENT_POLICY_NO_ELIGIBLE_ROUTE",
                )
        out.append(row)

    preferred_after = sum(bool(row.get("preferred_email_route")) for row in out)
    return out, {
        "accounts_with_preferred_before": preferred_before,
        "accounts_with_preferred_after": preferred_after,
        "accounts_demoted": accounts_demoted,
        "routes_rejected": sum(rejected_routes.values()),
        **{
            f"routes_rejected_{reason}": rejected_routes[reason]
            for reason, _ in _IDENTITY_GUARD_BLOCKERS
        },
    }


def _load_prior_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    digest = hashlib.sha256()
    rows: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for raw in handle:
            digest.update(raw)
            text = raw.decode("utf-8").strip()
            if not text:
                continue
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("prior contacts projection contains a non-object row")
            rows.append(value)
    return rows, digest.hexdigest()


def _enum(enum_type: type[Any], raw: Any, default: Any) -> Any:
    try:
        return enum_type(raw)
    except (TypeError, ValueError):
        return default


def _candidate_from_stored(raw: dict[str, Any], account_id: str) -> DecisionUnitCandidate | None:
    candidate_id = str(raw.get("candidate_id") or "").strip()
    if not candidate_id:
        return None
    return DecisionUnitCandidate(
        candidate_id=candidate_id,
        company_entity_id=str(raw.get("company_entity_id") or account_id),
        person_id=str(raw.get("person_id") or ""),
        person_name=str(raw.get("person_name") or "").strip() or None,
        observed_roles=[str(item) for item in (raw.get("observed_roles") or []) if item],
        decision_role_class=_enum(
            DecisionRoleClass,
            raw.get("decision_role_class"),
            DecisionRoleClass.UNKNOWN,
        ),
        identity_confidence=_enum(
            ConfidenceLevel,
            raw.get("identity_confidence"),
            ConfidenceLevel.UNKNOWN,
        ),
        role_confidence=_enum(
            ConfidenceLevel,
            raw.get("role_confidence"),
            ConfidenceLevel.UNKNOWN,
        ),
        suitability=_enum(
            ConfidenceLevel,
            raw.get("suitability"),
            ConfidenceLevel.UNKNOWN,
        ),
    )


def _route_from_stored(raw: dict[str, Any], account_id: str) -> ReachabilityRoute | None:
    route_id = str(raw.get("route_id") or "").strip()
    channel_value = str(raw.get("channel_value") or "").strip()
    if not route_id or not channel_value:
        return None
    return ReachabilityRoute(
        route_id=route_id,
        company_entity_id=str(raw.get("company_entity_id") or account_id),
        channel_type=_enum(ChannelType, raw.get("channel_type"), ChannelType.OTHER_PUBLIC_BUSINESS_ROUTE),
        reachability_class=_enum(
            ReachabilityClass,
            raw.get("reachability_class"),
            ReachabilityClass.R0_NO_ACTIONABLE_ROUTE,
        ),
        action_mode=_enum(ActionMode, raw.get("action_mode"), ActionMode.NEEDS_ENRICHMENT),
        decision_unit_candidate_id=str(raw.get("decision_unit_candidate_id") or "").strip() or None,
        target_role=str(raw.get("target_role") or "").strip() or None,
        channel_value=channel_value,
        route_relation=_enum(
            RouteRelation,
            raw.get("route_relation"),
            RouteRelation.ACCOUNT_LEVEL_ONLY,
        ),
        epistemic_class=_enum(
            EpistemicClass,
            raw.get("epistemic_class"),
            EpistemicClass.UNKNOWN,
        ),
        source_type=str(raw.get("source_type") or "").strip() or None,
        source_url=str(raw.get("source_url") or "").strip() or None,
        evidence_ids=[str(item) for item in (raw.get("evidence_ids") or []) if item],
        route_confidence=_enum(
            ConfidenceLevel,
            raw.get("route_confidence"),
            ConfidenceLevel.UNKNOWN,
        ),
        freshness=_enum(FreshnessState, raw.get("freshness"), FreshnessState.UNKNOWN),
        ownership=_enum(OwnershipStatus, raw.get("ownership"), OwnershipStatus.UNKNOWN),
        suppression=_enum(SuppressionState, raw.get("suppression"), SuppressionState.NONE),
        reason_codes=[str(item) for item in (raw.get("reason_codes") or []) if item],
        observed_at=str(raw.get("observed_at") or "").strip() or None,
        suitability=_enum(
            ConfidenceLevel,
            raw.get("suitability"),
            ConfidenceLevel.UNKNOWN,
        ),
        extra=dict(raw.get("extra") or {}) if isinstance(raw.get("extra"), dict) else {},
    )


def _current_policy_projection(
    stored_projection: dict[str, Any],
    *,
    account: dict[str, Any],
) -> dict[str, Any]:
    """Reclassify immutable discovery evidence under the current route policy.

    Crawling and classification are deliberately separate: a policy repair must
    apply to already collected evidence without rewriting signed job outputs or
    spending another public-search budget.
    """
    account_id = str(account.get("company_entity_id") or account.get("cnpj") or "").strip()
    if not account_id:
        return stored_projection
    candidates = [
        candidate
        for raw in (account.get("candidates") or [])
        if isinstance(raw, dict)
        if (candidate := _candidate_from_stored(raw, account_id)) is not None
    ]
    routes = [
        route
        for raw in (account.get("routes") or [])
        if isinstance(raw, dict)
        if (route := _route_from_stored(raw, account_id)) is not None
    ]
    restored = AccountInvestigation(
        company_entity_id=account_id,
        cnpj=str(account.get("cnpj") or account_id),
        legal_name=str(account.get("legal_name") or "").strip() or None,
        service_context=str(account.get("service_context") or "generic"),
        why_now=str(account.get("why_now") or "").strip() or None,
        candidates=candidates,
        routes=routes,
        policy_version=str(account.get("policy_version") or "dui.policy.v1"),
        extra=dict(account.get("extra") or {}) if isinstance(account.get("extra"), dict) else {},
    )
    ranking = classify_account_email_routes(
        restored,
        named_person_safe=is_email_safe_for_warmbly,
    )
    current = dict(stored_projection)
    current.update(ranking.to_dict())
    current["contacts"] = [feed_contact_from_classified(item) for item in ranking.classified_routes]
    return current


def build_contact_projection(
    queue: ContactDiscoveryQueue,
    *,
    cohort_id: str,
    prior_rows: list[dict[str, Any]] | None = None,
    prior_evidence: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    jobs = queue.inspect(cohort_id=cohort_id)
    progress = queue.progress(cohort_id=cohort_id)
    rows: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    route_classes: Counter[str] = Counter()
    preferred_classes: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    integrity_failures: Counter[str] = Counter()
    terminal_jobs = 0

    for job in jobs:
        status = str(job.get("status") or "")
        if status not in TERMINAL_JOB_STATUSES:
            continue
        terminal_jobs += 1
        payload, integrity_error = _read_verified_output(job)
        if integrity_error:
            if status == "SUCCEEDED":
                integrity_failures[integrity_error] += 1
                continue
            reason = str(job.get("last_reason_code") or integrity_error)
            row = _blocked_row(job, reason)
            rows.append(row)
            states["BLOCKED_WITH_REASON"] += 1
            blockers[reason] += 1
            continue

        # Non-success terminal jobs are explicit account outcomes even when a
        # prior retry left a well-formed partial output behind.  Never let that
        # stale attempt payload hide the durable DLQ/BLOCKED/CANCELLED reason,
        # and never require a contact artifact in order to project a blocker.
        if status != "SUCCEEDED":
            reason = str(job.get("last_reason_code") or status)
            row = _blocked_row(job, reason)
            rows.append(row)
            states["BLOCKED_WITH_REASON"] += 1
            blockers[reason] += 1
            continue

        state = str((payload or {}).get("enrichment_state") or "")
        reason = str((payload or {}).get("enrichment_reason") or "")
        if state not in ENRICHMENT_TERMINALS:
            integrity_failures["OUTPUT_ENRICHMENT_TERMINAL_MISSING"] += 1
            continue
        projection = (payload or {}).get("contact_projection")
        projection = projection if isinstance(projection, dict) else {}
        account = (payload or {}).get("account")
        account = account if isinstance(account, dict) else {}
        projection = _current_policy_projection(projection, account=account)
        projection = attach_projection_evidence(projection, account=account)
        domain = ((account.get("extra") or {}).get("domain_resolution") or {}).get("canonical_domain")
        contacts, rejected_missing_observed_at = _rank_publishable_contacts(
            [dict(item) for item in (projection.get("contacts") or []) if isinstance(item, dict)],
            account_id=str(job["canonical_account_id"]),
            official_domain=str(domain or "").strip() or None,
        )
        preferred = next(
            (item for item in contacts if item.get("preferred_initial") and item.get("controlled_email_eligible")),
            None,
        )
        if status == "SUCCEEDED" and preferred:
            state = "EMAIL_ROUTE_READY"
            reason = "CONTROLLED_EMAIL_ROUTE_SELECTED"
        elif status == "SUCCEEDED" and state == "EMAIL_ROUTE_READY":
            state = "BLOCKED_WITH_REASON"
            reason = (
                "CONTACT_ROUTE_MISSING_OBSERVED_AT"
                if rejected_missing_observed_at
                else "CURRENT_POLICY_NO_ELIGIBLE_ROUTE"
            )
        row = {
            "cnpj14": str(job["canonical_account_id"]),
            "canonical_account_id": str(job["canonical_account_id"]),
            "contacts": contacts,
            "preferred_email_route": (
                _preferred_route_from_contact(str(job["canonical_account_id"]), preferred)
                if preferred is not None
                else None
            ),
            "enrichment_state": state,
            "enrichment_reason": reason,
            "official_domain": domain,
            "contact_discovery_job_id": int(job["id"]),
            "contact_discovery_output_hash": job.get("output_hash"),
            "contact_discovery_policy_version": job.get("discovery_policy_version"),
            "contact_discovery_input_evidence_version": job.get("input_evidence_version"),
        }
        if rejected_missing_observed_at:
            row["publication_guard_failures"] = {
                "MISSING_OBSERVED_AT": rejected_missing_observed_at,
            }
        rows.append(row)
        states[state] += 1
        if state == "BLOCKED_WITH_REASON":
            blockers[reason or "UNSPECIFIED"] += 1
        if preferred:
            preferred_classes[str(preferred.get("route_class") or "UNKNOWN")] += 1
        for contact in contacts:
            route_classes[str(contact.get("route_class") or "UNKNOWN")] += 1
            sources[str(contact.get("source") or "UNKNOWN")] += 1

    rows.sort(key=lambda row: str(row["cnpj14"]))
    reconciliation: dict[str, Any] | None = None
    if prior_rows is not None:
        rows, reconciliation_metrics = reconcile_prior_contact_rows(rows, prior_rows)
        reconciliation = {**(prior_evidence or {}), **reconciliation_metrics}
    rows, identity_gate_metrics = apply_authoritative_identity_gate(rows)
    # Reconciliation and the whole-population identity gate both change
    # derived account outcomes. Recompute the report from what is publishable.
    states = Counter(str(row.get("enrichment_state") or "UNKNOWN") for row in rows)
    blockers = Counter(
        str(row.get("enrichment_reason") or "UNSPECIFIED")
        for row in rows
        if row.get("enrichment_state") == "BLOCKED_WITH_REASON"
    )
    route_classes = Counter(
        str(contact.get("route_class") or "UNKNOWN")
        for row in rows
        for contact in (row.get("contacts") or [])
        if isinstance(contact, dict)
    )
    preferred_classes = Counter(
        str((row.get("preferred_email_route") or {}).get("route_class") or "UNKNOWN")
        for row in rows
        if row.get("preferred_email_route")
    )
    sources = Counter(
        str(contact.get("source") or "UNKNOWN")
        for row in rows
        for contact in (row.get("contacts") or [])
        if isinstance(contact, dict)
    )
    denominator = int(progress.get("denominator") or len(jobs))
    population_contract = progress.get("population_contract")
    population_contract = population_contract if isinstance(population_contract, dict) else {}
    population_count = int(
        population_contract.get("population_count") or population_contract.get("population_total") or denominator
    )
    membership = canonical_target_membership([str(job.get("canonical_account_id") or "") for job in jobs])
    declared_membership_count = population_contract.get("membership_count")
    declared_membership_hash = population_contract.get("membership_hash")
    membership_contract_matches = (
        declared_membership_count is None or int(declared_membership_count) == membership["population_count"]
    ) and (declared_membership_hash is None or str(declared_membership_hash) == membership["membership_hash"])
    terminal_projection_total = sum(states.values())
    terminal_account_count = len({str(row["canonical_account_id"]) for row in rows})
    population_contract_matches_denominator = population_count == denominator
    terminal_equation_holds = (
        population_contract_matches_denominator
        and membership_contract_matches
        and membership["population_count"] == denominator
        and terminal_projection_total == denominator
        and terminal_account_count == denominator
        and not integrity_failures
    )
    projection_hash = canonical_payload_hash(rows)
    publication_guard_failures: Counter[str] = Counter()
    for row in rows:
        for guard, count in (row.get("publication_guard_failures") or {}).items():
            publication_guard_failures[str(guard)] += int(count or 0)
    report = {
        "schema_id": "confenge.contact_discovery.projection_report.v1",
        "generated_at": _utcnow(),
        "cohort_id": cohort_id,
        "denominator": denominator,
        "population_count": population_count,
        "population_hash": population_contract.get("population_hash") or population_contract.get("selection_hash"),
        "membership_schema_version": membership["schema_version"],
        "membership_identity_key": membership["identity_key"],
        "membership_hash_algorithm": membership["hash_algorithm"],
        "membership_count": membership["population_count"],
        "membership_hash": membership["membership_hash"],
        "duplicate_member_count": membership["duplicate_member_count"],
        "membership_contract_matches_population": membership_contract_matches,
        "population_as_of": population_contract.get("population_as_of"),
        "target_fit_mode": population_contract.get("target_fit_mode"),
        "target_fit_classifier_sha": population_contract.get("target_fit_classifier_sha"),
        "target_fit_classifier_shas": population_contract.get("target_fit_classifier_shas") or [],
        "sector_classifier_sha": population_contract.get("sector_classifier_sha"),
        "sector_classifier_shas": population_contract.get("sector_classifier_shas") or [],
        "population_contract_matches_denominator": population_contract_matches_denominator,
        "job_status_counts": progress.get("counts") or {},
        "terminal_jobs": terminal_jobs,
        "terminal_account_count": terminal_account_count,
        "effectively_enriched_total": terminal_projection_total,
        "terminal_coverage_complete": terminal_equation_holds,
        "terminal_equation": {
            "population_count": population_count,
            "job_denominator": denominator,
            "terminal_projection_total": terminal_projection_total,
            "terminal_account_count": terminal_account_count,
            "holds": terminal_equation_holds,
        },
        "enrichment_states": dict(sorted(states.items())),
        "blockers": dict(sorted(blockers.items())),
        "accounts_with_any_email": sum(bool(row["contacts"]) for row in rows),
        "accounts_with_preferred_route": sum(bool(row.get("preferred_email_route")) for row in rows),
        "route_class_distribution": dict(sorted(route_classes.items())),
        "preferred_route_class_distribution": dict(sorted(preferred_classes.items())),
        "provenance_source_distribution": dict(sorted(sources.items())),
        "integrity_failures": dict(sorted(integrity_failures.items())),
        "publication_guard_failures": dict(sorted(publication_guard_failures.items())),
        "authoritative_identity_gate": identity_gate_metrics,
        "projection_hash": projection_hash,
        "controlled_email_policy_version": CONTROLLED_EMAIL_POLICY_VERSION,
        "policy_version": progress.get("policy_version"),
        "input_evidence_version": progress.get("input_evidence_version"),
        "code_sha": progress.get("code_sha"),
        "search_backend": progress.get("search_backend"),
        "budget_version": progress.get("budget_version"),
    }
    if reconciliation is not None:
        report["durable_reconciliation"] = reconciliation
    return rows, report


def write_contact_projection(
    queue: ContactDiscoveryQueue,
    *,
    cohort_id: str,
    output_path: Path,
    report_path: Path,
    allow_partial: bool = False,
    prior_contacts_path: Path | None = None,
) -> dict[str, Any]:
    prior_rows: list[dict[str, Any]] | None = None
    prior_evidence: dict[str, Any] | None = None
    if prior_contacts_path is not None:
        prior_rows, prior_sha256 = _load_prior_rows(prior_contacts_path)
        prior_evidence = {
            "prior_contacts_path": str(prior_contacts_path),
            "prior_contacts_sha256": prior_sha256,
        }
    rows, report = build_contact_projection(
        queue,
        cohort_id=cohort_id,
        prior_rows=prior_rows,
        prior_evidence=prior_evidence,
    )
    if not allow_partial and not report["terminal_coverage_complete"]:
        return {**report, "written": False, "reason": "TERMINAL_COVERAGE_INCOMPLETE"}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, report)
    return {
        **report,
        "written": True,
        "contacts_path": str(output_path),
        "report_path": str(report_path),
    }
