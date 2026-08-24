"""Verified derived projection from durable discovery jobs into bridge contacts."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.batch_contact_metadata import attach_projection_evidence
from scripts.decision_unit_intelligence.batch_queue import ContactDiscoveryQueue, canonical_payload_hash
from scripts.decision_unit_intelligence.controlled_email import (
    CONTROLLED_EMAIL_POLICY_VERSION,
    classify_account_email_routes,
    feed_contact_from_classified,
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
ENRICHMENT_TERMINALS = frozenset(
    {"EMAIL_ROUTE_READY", "NO_PUBLIC_EMAIL_FOUND", "BLOCKED_WITH_REASON"}
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
        contacts = [dict(item) for item in (projection.get("contacts") or []) if isinstance(item, dict)]
        preferred = projection.get("preferred_initial_route")
        preferred = preferred if isinstance(preferred, dict) else None
        if status == "SUCCEEDED" and preferred:
            state = "EMAIL_ROUTE_READY"
            reason = "CONTROLLED_EMAIL_ROUTE_SELECTED"
        elif status == "SUCCEEDED" and state == "EMAIL_ROUTE_READY":
            state = "BLOCKED_WITH_REASON"
            reason = "CURRENT_POLICY_NO_ELIGIBLE_ROUTE"
        domain = ((account.get("extra") or {}).get("domain_resolution") or {}).get("canonical_domain")
        row = {
            "cnpj14": str(job["canonical_account_id"]),
            "canonical_account_id": str(job["canonical_account_id"]),
            "contacts": contacts,
            "preferred_email_route": preferred,
            "enrichment_state": state,
            "enrichment_reason": reason,
            "official_domain": domain,
            "contact_discovery_job_id": int(job["id"]),
            "contact_discovery_output_hash": job.get("output_hash"),
            "contact_discovery_policy_version": job.get("discovery_policy_version"),
            "contact_discovery_input_evidence_version": job.get("input_evidence_version"),
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
    denominator = int(progress.get("denominator") or len(jobs))
    population_contract = progress.get("population_contract")
    population_contract = population_contract if isinstance(population_contract, dict) else {}
    population_count = int(
        population_contract.get("population_count")
        or population_contract.get("population_total")
        or denominator
    )
    terminal_projection_total = sum(states.values())
    terminal_account_count = len({str(row["canonical_account_id"]) for row in rows})
    population_contract_matches_denominator = population_count == denominator
    terminal_equation_holds = (
        population_contract_matches_denominator
        and terminal_projection_total == denominator
        and terminal_account_count == denominator
        and not integrity_failures
    )
    projection_hash = canonical_payload_hash(rows)
    report = {
        "schema_id": "confenge.contact_discovery.projection_report.v1",
        "generated_at": _utcnow(),
        "cohort_id": cohort_id,
        "denominator": denominator,
        "population_count": population_count,
        "population_hash": population_contract.get("population_hash")
        or population_contract.get("selection_hash"),
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
        "projection_hash": projection_hash,
        "controlled_email_policy_version": CONTROLLED_EMAIL_POLICY_VERSION,
        "policy_version": progress.get("policy_version"),
        "input_evidence_version": progress.get("input_evidence_version"),
        "code_sha": progress.get("code_sha"),
        "search_backend": progress.get("search_backend"),
        "budget_version": progress.get("budget_version"),
    }
    return rows, report


def write_contact_projection(
    queue: ContactDiscoveryQueue,
    *,
    cohort_id: str,
    output_path: Path,
    report_path: Path,
    allow_partial: bool = False,
) -> dict[str, Any]:
    rows, report = build_contact_projection(queue, cohort_id=cohort_id)
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
