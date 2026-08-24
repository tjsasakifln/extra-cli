"""Approved snapshot gate for a contact-discovery cohort."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.batch_queue import ContactDiscoveryQueue, canonical_payload_hash
from scripts.decision_unit_intelligence.repository import write_json

PUBLISHABLE = {"SUCCEEDED", "BLOCKED", "DLQ", "CANCELLED"}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reconcile_outputs(jobs: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for job in jobs:
        if job["status"] not in PUBLISHABLE:
            continue
        if job["status"] in {"BLOCKED", "DLQ", "CANCELLED"}:
            continue
        pointer = job.get("output_pointer")
        digest = job.get("output_hash")
        if not pointer or not digest:
            errors.append(f"job {job['id']} missing output pointer/hash")
            continue
        path = Path(str(pointer))
        if not path.is_file():
            errors.append(f"job {job['id']} output missing on disk: {pointer}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        recomputed = canonical_payload_hash(payload)
        if recomputed != digest:
            errors.append(f"job {job['id']} output hash mismatch")
    return errors


def evaluate_publish(queue: ContactDiscoveryQueue, *, cohort_id: str) -> dict[str, Any]:
    progress = queue.progress(cohort_id=cohort_id)
    jobs = queue.inspect(cohort_id=cohort_id)
    duplicates = queue.duplicate_identities(cohort_id=cohort_id)
    reasons: list[str] = []
    if not progress["closable"]:
        reasons.append("denominator has non-terminal jobs")
    if duplicates:
        reasons.append("duplicate jobs for same account×policy×input")
    missing_meta = [
        job["id"]
        for job in jobs
        if not (
            job.get("discovery_policy_version")
            and job.get("code_sha")
            and job.get("search_backend")
            and job.get("budget_version")
        )
    ]
    if missing_meta:
        reasons.append(f"jobs missing policy/sha/backend/budget: {missing_meta[:8]}")
    reasons.extend(reconcile_outputs(jobs))
    return {
        "cohort_id": cohort_id,
        "approved": not reasons,
        "reject_reasons": reasons,
        "progress": progress,
        "job_count": len(jobs),
        "duplicates": duplicates,
    }


def publish_snapshot(
    queue: ContactDiscoveryQueue,
    *,
    cohort_id: str,
    output_root: Path,
    allow_partial: bool = False,
) -> dict[str, Any]:
    evaluation = evaluate_publish(queue, cohort_id=cohort_id)
    approved = bool(evaluation["approved"])
    if not approved and not allow_partial:
        snapshot_id = f"reject-{uuid.uuid4().hex[:12]}"
        pointer = str(Path(output_root) / cohort_id / f"{snapshot_id}.json")
        payload = {
            "schema_id": "confenge.contact_discovery.snapshot.v1",
            "snapshot_id": snapshot_id,
            "approved": False,
            "created_at": _now_iso(),
            **evaluation,
        }
        write_json(Path(pointer), payload)
        digest = canonical_payload_hash(payload)
        queue.mark_cohort_published(
            cohort_id=cohort_id,
            snapshot_id=snapshot_id,
            pointer=pointer,
            content_hash=digest,
            approved=False,
            status_counts=evaluation["progress"]["counts"],
            reject_reason="; ".join(evaluation["reject_reasons"]),
        )
        return {**payload, "pointer": pointer, "content_hash": digest}

    snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
    jobs = queue.inspect(cohort_id=cohort_id)
    payload = {
        "schema_id": "confenge.contact_discovery.snapshot.v1",
        "snapshot_id": snapshot_id,
        "approved": approved,
        "created_at": _now_iso(),
        "progress": evaluation["progress"],
        "jobs": [
            {
                "id": job["id"],
                "canonical_account_id": job["canonical_account_id"],
                "status": job["status"],
                "reason_code": job["last_reason_code"],
                "output_pointer": job["output_pointer"],
                "output_hash": job["output_hash"],
                "policy_version": job["discovery_policy_version"],
                "code_sha": job["code_sha"],
                "search_backend": job["search_backend"],
                "budget_version": job["budget_version"],
            }
            for job in jobs
        ],
        "reject_reasons": evaluation["reject_reasons"],
    }
    pointer = str(Path(output_root) / cohort_id / f"{snapshot_id}.json")
    write_json(Path(pointer), payload)
    digest = canonical_payload_hash(payload)
    queue.mark_cohort_published(
        cohort_id=cohort_id,
        snapshot_id=snapshot_id,
        pointer=pointer,
        content_hash=digest,
        approved=approved,
        status_counts=evaluation["progress"]["counts"],
        reject_reason=None if approved else "; ".join(evaluation["reject_reasons"]),
    )
    return {**payload, "pointer": pointer, "content_hash": digest}
