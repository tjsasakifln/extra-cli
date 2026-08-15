"""Factory-spine runtime: freshness enqueue, leased workers and launch.

Refs #246 #247 #256 #268 #269 #270 #272 #279
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.worker import AdmissionLimits, admission_blockers
from scripts.factory_spine.contracts import (
    DEFAULT_CAPABILITY,
    apply_surface_revalidation,
    classify_discovery_surface,
    decide_resilience,
    job_idempotency_key,
    plan_freshness_enqueue,
    publish_coverage_cell,
)
from scripts.factory_spine.portal import interpret_portal_fetch
from scripts.factory_spine.store import FactoryStore
from scripts.source_registry.continuous_inventory import SurfaceObservation


def apply_freshness_plan(store: FactoryStore, decisions: list[Any], *, now: datetime) -> dict[str, Any]:
    """Refs #268 — billable pairs enqueue once; others keep a dated next_run."""
    queued = 0
    existing = 0
    deferred = 0
    window_start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(hours=24)
    for decision in decisions:
        if not decision.billable:
            deferred += 1
            continue
        _job, created = store.enqueue(
            entity_id=decision.entity_id,
            canonical_entity_key=decision.canonical_entity_key,
            source=decision.source,
            capability=decision.capability,
            domain_key=decision.source,
            binding_version=decision.binding_version,
            window_start=window_start,
            window_end=window_end,
            freshness_deadline=decision.freshness_deadline,
            next_run_at=decision.next_run_at,
        )
        if created:
            queued += 1
        else:
            existing += 1
    return {
        "queued": queued,
        "existing": existing,
        "deferred": deferred,
        "pair_count": len(decisions),
        "fully_reconciled": queued + existing + deferred == len(decisions),
    }


def launch_spine(
    state_dir: Path,
    *,
    entity_key: str = "extra-canonical-0001",
    entity_id: int = 1,
    source: str = "transparencia",
    worker_id: str = "factory-spine-local",
    now: datetime | None = None,
    admission: AdmissionLimits | None = None,
) -> dict[str, Any]:
    """Enqueue/inspect one job, archive raw, persist a document and a failure."""
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    store = FactoryStore(Path(state_dir))
    blockers = admission_blockers(admission or AdmissionLimits(), state_path=store.root)
    if blockers:
        return {"ok": False, "status": "backpressure", "blockers": blockers}

    observation = SurfaceObservation(
        kind="transparency",
        canonical_url="https://transparencia.example.test/licitacoes",
        platform="generic-public",
        anchor_url="https://example.test/",
        method="factory_spine_launch",
        http_status=200,
    )
    status, safe_url, domain = classify_discovery_surface(observation, known_domains=set())
    current, history = apply_surface_revalidation(
        None,
        status=status,
        canonical_url=safe_url,
        domain=domain,
        platform=observation.platform,
    )
    coverage = publish_coverage_cell(
        canonical_entity_key=entity_key,
        source=source,
        status="FAILED",
        executed=True,
        applicability=True,
        applicability_reason="launch_probe_requires_structured_failure_before_zero",
        request_completed=True,
        scope_complete=False,
        pagination_reconciled=False,
        records_observed=0,
        pages_fetched=1,
        pages_expected=2,
        canonical_url=safe_url,
        http_statuses=(403,),
        checked_at=clock,
        next_action="retry_after_policy_delay",
    )
    html = (
        "<table class='licitacoes'><tr><td>Edital 01/2026</td>"
        "<td><a href='/docs/edital-01.pdf'>PDF</a></td></tr></table>"
    )
    portal = interpret_portal_fetch(
        url="https://transparencia.example.test/licitacoes?token=secret-token",
        http_status=200,
        body=html,
        fetched_at=clock,
    )
    decisions = plan_freshness_enqueue(
        [
            {
                "canonical_entity_key": entity_key,
                "entity_id": entity_id,
                "source": source,
                "capability": DEFAULT_CAPABILITY,
                "applicability": "APPLICABLE",
                "reason": "freshness_due",
                "binding_version": "launch-v1",
            }
        ],
        now=clock,
        expected_entities=1,
    )
    enqueue_summary = apply_freshness_plan(store, decisions, now=clock)
    window_start = clock.replace(minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(hours=24)
    job = store.find_by_idempotency(
        job_idempotency_key(
            canonical_entity_key=entity_key,
            source=source,
            capability=DEFAULT_CAPABILITY,
            window_start=window_start,
            window_end=window_end,
            binding_version="launch-v1",
        )
    )
    if job is None:
        raise RuntimeError("freshness enqueue did not persist a job")
    created = bool(enqueue_summary["queued"])
    if job["status"] in {"succeeded", "failed", "blocked"}:
        attempt = job["attempts"][-1] if job["attempts"] else {}
        raw_meta = store.archive_raw(
            source=source,
            run_id=str(attempt.get("run_id") or "inspect"),
            request_scope=f"{entity_key}:{source}",
            payload=html,
            url="https://transparencia.example.test/licitacoes?token=secret-token",
            http_status=200,
            page=1,
            crawl_job_attempt_id=attempt.get("id"),
        )
        failure = store.record_structured_failure(
            source=source,
            run_id=str(attempt.get("run_id") or "inspect"),
            request_scope=f"{entity_key}:{source}",
            stage="probe",
            error="HTTP 403",
            http_status=403,
            url="https://transparencia.example.test/area-restrita?token=secret-token",
            page=1,
            cursor="page=1",
            attempt_no=int(job.get("attempt_count") or 1),
            job_id=int(job["id"]),
            crawl_job_attempt_id=attempt.get("id"),
        )
        document = store.persist_document(
            entity_id=entity_id,
            source=source,
            official_id="edital-01-2026",
            body=b"edital-01-2026-factory-spine-body",
            official_url="https://transparencia.example.test/docs/edital-01.pdf",
            process_official_id="proc-01-2026",
            crawl_job_attempt_id=attempt.get("id"),
        )
        return _launch_payload(
            ok=True,
            created=created,
            job=job,
            attempt=attempt,
            raw_meta=raw_meta,
            failure=failure,
            coverage=coverage,
            portal=portal.as_dict(),
            discovery={"status": current.status, "history": [item.version_no for item in history]},
            enqueue=enqueue_summary,
            resilience=decide_resilience(
                http_status=403,
                error="HTTP 403",
                attempt=1,
                max_attempts=5,
            ),
            document=document,
        )

    claimed = store.claim(worker_id=worker_id, now=clock)
    if not claimed:
        return {"ok": False, "status": "idle", "job_id": job["id"], "created": created}
    claimed_job = claimed[0]
    attempt = claimed_job["current_attempt"]
    store.heartbeat(int(claimed_job["id"]), worker_id=worker_id, cursor={"page": 1}, now=clock)
    raw_meta = store.archive_raw(
        source=source,
        run_id=attempt["run_id"],
        request_scope=f"{entity_key}:{source}",
        payload=html,
        url="https://transparencia.example.test/licitacoes?token=secret-token",
        http_status=200,
        page=1,
        crawl_job_attempt_id=attempt["id"],
    )
    document = store.persist_document(
        entity_id=entity_id,
        source=source,
        official_id="edital-01-2026",
        body=b"edital-01-2026-factory-spine-body",
        official_url="https://transparencia.example.test/docs/edital-01.pdf",
        process_official_id="proc-01-2026",
        crawl_job_attempt_id=attempt["id"],
    )
    failure = store.record_structured_failure(
        source=source,
        run_id=attempt["run_id"],
        request_scope=f"{entity_key}:{source}",
        stage="probe",
        error="HTTP 403",
        http_status=403,
        url="https://transparencia.example.test/area-restrita?token=secret-token",
        page=1,
        cursor="page=1",
        attempt_no=claimed_job["attempt_count"],
        job_id=int(claimed_job["id"]),
        crawl_job_attempt_id=attempt["id"],
    )
    resilience = decide_resilience(http_status=403, error="HTTP 403", attempt=1, max_attempts=5)
    finished = store.finish(
        int(claimed_job["id"]),
        worker_id=worker_id,
        outcome="succeeded",
        cursor={"page": 1, "document_version_id": document["document_version_id"]},
        metrics={"pages_fetched": 1, "raw_sha256": raw_meta["body_sha256"]},
        now=clock,
    )
    if not finished:
        raise RuntimeError("terminal job transition failed")
    inspected = store.inspect(int(claimed_job["id"]))
    if inspected is None:
        raise RuntimeError("job disappeared after terminal write")
    return _launch_payload(
        ok=True,
        created=created,
        job=inspected,
        attempt=attempt,
        raw_meta=raw_meta,
        failure=failure,
        coverage=coverage,
        portal=portal.as_dict(),
        discovery={"status": current.status, "history": [item.version_no for item in history]},
        enqueue=enqueue_summary,
        resilience=resilience,
        document=document,
    )


def _launch_payload(
    *,
    ok: bool,
    created: bool,
    job: dict[str, Any],
    attempt: dict[str, Any],
    raw_meta: dict[str, Any],
    failure: dict[str, Any],
    coverage: dict[str, Any],
    portal: dict[str, Any],
    discovery: dict[str, Any],
    enqueue: dict[str, Any],
    resilience: Any,
    document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": job.get("status"),
        "created": created,
        "job_id": job.get("id"),
        "attempt_id": attempt.get("id"),
        "run_id": attempt.get("run_id"),
        "idempotency_key": job.get("idempotency_key"),
        "raw_pointer": raw_meta.get("body_uri"),
        "raw_sha256": raw_meta.get("body_sha256"),
        "error_class": failure["event"]["error_class"],
        "error_fingerprint": failure["fingerprint"],
        "coverage_status": coverage["status"],
        "portal_terminal": portal["terminal"],
        "discovery_status": discovery["status"],
        "enqueue": enqueue,
        "resilience_action": resilience.action,
        "resilience_terminal": resilience.terminal,
        "document_version_id": (document or {}).get("document_version_id"),
    }
