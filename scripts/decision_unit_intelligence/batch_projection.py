"""Verified derived projection from durable discovery jobs into bridge contacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.batch_queue import ContactDiscoveryQueue
from scripts.decision_unit_intelligence.repository import write_json

TERMINAL_JOB_STATUSES = frozenset({"SUCCEEDED", "BLOCKED", "DLQ", "CANCELLED"})
ENRICHMENT_TERMINALS = frozenset(
    {"EMAIL_ROUTE_READY", "NO_PUBLIC_EMAIL_FOUND", "BLOCKED_WITH_REASON"}
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _content_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    if expected and _content_hash(payload) != expected:
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


def _route_index(account: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_mailbox: dict[str, dict[str, Any]] = {}
    for raw in account.get("routes") or []:
        if not isinstance(raw, dict):
            continue
        route = dict(raw)
        route_id = str(route.get("route_id") or "").strip()
        mailbox = str(route.get("channel_value") or "").strip().lower()
        if route_id:
            by_id[route_id] = route
        if mailbox and "@" in mailbox:
            by_mailbox[mailbox] = route
    return by_id, by_mailbox


def _attach_route_evidence(
    contacts: list[dict[str, Any]],
    *,
    account: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join classifier output back to its durable route evidence.

    This projection owns transport metadata; the frozen eligibility policy
    remains untouched. The downstream mapper already preserves source,
    provenance and observed timestamps, then re-stamps route class/rank using
    the active campaign policy.
    """
    by_id, by_mailbox = _route_index(account)
    enriched: list[dict[str, Any]] = []
    for raw in contacts:
        contact = dict(raw)
        route_id = str(contact.get("source_contact_id") or contact.get("route_id") or "").strip()
        mailbox = str(contact.get("email") or contact.get("mailbox") or "").strip().lower()
        route = by_id.get(route_id) or by_mailbox.get(mailbox)
        if route is None:
            enriched.append(contact)
            continue

        source_type = str(route.get("source_type") or "").strip() or None
        source_url = str(route.get("source_url") or "").strip() or None
        observed_at = str(route.get("observed_at") or "").strip() or None
        evidence_ids = [str(item) for item in (route.get("evidence_ids") or []) if item]
        epistemic = str(route.get("epistemic_class") or "").strip() or None
        target_role = str(route.get("target_role") or "").strip() or None
        ownership = str(route.get("ownership") or "").strip() or None
        freshness = str(route.get("freshness") or "").strip() or None
        suppression = str(route.get("suppression") or "").strip() or None

        if source_type:
            contact["source"] = source_type
            contact["source_type"] = source_type
        if source_url:
            contact["source_url"] = source_url
        if observed_at:
            contact["observed_at"] = observed_at
        if evidence_ids:
            contact["evidence_ids"] = evidence_ids
        source_reference = source_url or (evidence_ids[0] if evidence_ids else None)
        if source_reference:
            contact["source_reference"] = source_reference
        if target_role:
            contact["mailbox_department"] = target_role
            contact.setdefault("role", target_role)
            contact.setdefault("role_class", target_role)
        if ownership:
            contact["ownership_status"] = ownership
        if freshness:
            contact["route_freshness"] = freshness
        if suppression:
            contact["route_suppression"] = suppression
        if epistemic:
            contact["provenance_class"] = epistemic

        raw_provenance = contact.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
        if source_type:
            provenance.setdefault("source_type", source_type)
        if source_url:
            provenance.setdefault("source_url", source_url)
        if observed_at:
            provenance.setdefault("observed_at", observed_at)
        if evidence_ids:
            provenance.setdefault("evidence_ids", evidence_ids)
        if epistemic:
            provenance.setdefault("epistemic_class", epistemic)
        if provenance:
            contact["provenance"] = provenance
        enriched.append(contact)
    return enriched


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

        state = str((payload or {}).get("enrichment_state") or "")
        reason = str((payload or {}).get("enrichment_reason") or "")
        if state not in ENRICHMENT_TERMINALS:
            integrity_failures["OUTPUT_ENRICHMENT_TERMINAL_MISSING"] += 1
            continue
        projection = (payload or {}).get("contact_projection")
        projection = projection if isinstance(projection, dict) else {}
        account = (payload or {}).get("account")
        account = account if isinstance(account, dict) else {}
        contacts = _attach_route_evidence(
            [dict(item) for item in (projection.get("contacts") or []) if isinstance(item, dict)],
            account=account,
        )
        preferred = projection.get("preferred_initial_route")
        preferred = preferred if isinstance(preferred, dict) else None
        if preferred:
            preferred_contacts = _attach_route_evidence(
                [{**preferred, "email": preferred.get("mailbox")}],
                account=account,
            )
            preferred = preferred_contacts[0] if preferred_contacts else preferred
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
    terminal_projection_total = sum(states.values())
    projection_hash = _content_hash(rows)
    report = {
        "schema_id": "confenge.contact_discovery.projection_report.v1",
        "generated_at": _utcnow(),
        "cohort_id": cohort_id,
        "denominator": denominator,
        "job_status_counts": progress.get("counts") or {},
        "terminal_jobs": terminal_jobs,
        "effectively_enriched_total": terminal_projection_total,
        "terminal_coverage_complete": terminal_projection_total == denominator,
        "enrichment_states": dict(sorted(states.items())),
        "blockers": dict(sorted(blockers.items())),
        "accounts_with_any_email": sum(bool(row["contacts"]) for row in rows),
        "accounts_with_preferred_route": sum(bool(row.get("preferred_email_route")) for row in rows),
        "route_class_distribution": dict(sorted(route_classes.items())),
        "preferred_route_class_distribution": dict(sorted(preferred_classes.items())),
        "provenance_source_distribution": dict(sorted(sources.items())),
        "integrity_failures": dict(sorted(integrity_failures.items())),
        "projection_hash": projection_hash,
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
