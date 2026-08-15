"""File-backed durable jobs, attempts, raw envelopes and document versions.

PostgreSQL remains the production authority (runtime_queue / raw_http_fetches /
document_versions). This store is the same contract without a payload column
and without writing bodies into git.

Refs #246 #247 #269 #272 #279
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.crawl.resilience.diagnostics import (
    FailureEvent,
    FailureRecorder,
    classify_failure,
    sanitize_text,
    sanitize_url,
)
from scripts.crawl.resilience.state import RawStore
from scripts.factory_spine.contracts import (
    JOB_TERMINALS,
    RankedJob,
    job_idempotency_key,
    rank_claim_candidates,
)
from scripts.process_documents.storage import store_blob


def utcnow() -> datetime:
    return datetime.now(UTC)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def persist_document_metadata(
    documents: list[dict[str, Any]],
    *,
    entity_id: int,
    source: str,
    official_id: str,
    sha256: str,
    size_bytes: int,
    body_uri: str,
    blob_confirmed: bool,
    official_url: str,
    process_official_id: str,
    mime_type: str | None = None,
    crawl_job_attempt_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Refs #272 — content change creates a version; never overwrite prior SHA."""
    if not blob_confirmed:
        raise ValueError("document job cannot succeed without a confirmed blob")
    if not body_uri.startswith("cas://"):
        raise ValueError("document body_uri must be content-addressed")
    if not sha256 or len(sha256) != 64:
        raise ValueError("document sha256 must be a 64-char hex digest")
    safe_url = sanitize_url(official_url)
    clock = (now or utcnow()).astimezone(UTC)
    existing_doc = next(
        (
            item
            for item in documents
            if item["source"] == source and item["official_id"] == official_id and item["entity_id"] == entity_id
        ),
        None,
    )
    if existing_doc is None:
        document_id = hashlib.sha256(f"{source}|{entity_id}|{official_id}".encode()).hexdigest()
        existing_doc = {
            "document_id": document_id,
            "entity_id": entity_id,
            "source": source,
            "official_id": official_id,
            "official_url": safe_url,
            "process_official_id": process_official_id,
            "versions": [],
        }
        documents.append(existing_doc)
    versions = list(existing_doc["versions"])
    same_hash = next((item for item in versions if item["sha256"] == sha256), None)
    if same_hash is not None:
        return {
            **same_hash,
            "document_id": existing_doc["document_id"],
            "changed": False,
            "blob_confirmed": True,
            "metadata_confirmed": True,
        }
    version_no = (versions[-1]["version_no"] + 1) if versions else 1
    version = {
        "document_id": existing_doc["document_id"],
        "document_version_id": f"{existing_doc['document_id']}:v{version_no}:{sha256[:16]}",
        "version_no": version_no,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "body_uri": body_uri,
        "mime_type": mime_type,
        "official_url": safe_url,
        "process_official_id": process_official_id,
        "crawl_job_attempt_id": crawl_job_attempt_id,
        "fetched_at": clock.isoformat(),
        "blob_confirmed": True,
        "metadata_confirmed": True,
        "changed": True,
    }
    versions.append(version)
    existing_doc["versions"] = versions
    existing_doc["official_url"] = safe_url
    return version


class FactoryStore:
    """Durable file-backed spine used by the CLI and contract tests."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs_path = root / "jobs.json"
        self.documents_path = root / "documents.json"
        self.lock_path = root / ".lock"
        self.attempts_path = root / "attempts.jsonl"
        self.raw = RawStore(root / "raw")
        self.failures = FailureRecorder(root / "failures.jsonl")

    def _read_jobs(self) -> list[dict[str, Any]]:
        payload = _load_json(self.jobs_path, {"jobs": []})
        return list(payload.get("jobs") or [])

    def _write_jobs(self, jobs: list[dict[str, Any]]) -> None:
        _atomic_json(self.jobs_path, {"jobs": jobs})

    def _read_documents(self) -> list[dict[str, Any]]:
        payload = _load_json(self.documents_path, {"documents": []})
        return list(payload.get("documents") or [])

    def _write_documents(self, documents: list[dict[str, Any]]) -> None:
        _atomic_json(self.documents_path, {"documents": documents})

    def enqueue(
        self,
        *,
        entity_id: int,
        canonical_entity_key: str,
        source: str,
        capability: str,
        domain_key: str,
        binding_version: str,
        window_start: datetime,
        window_end: datetime,
        freshness_deadline: datetime,
        next_run_at: datetime,
        priority: int = 0,
        cursor: dict[str, Any] | None = None,
        max_attempts: int = 5,
        domain_concurrency_limit: int = 1,
        billable: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        if not billable:
            raise ValueError("non-billable pairs must not create a crawl job")
        key = job_idempotency_key(
            canonical_entity_key=canonical_entity_key,
            source=source,
            capability=capability,
            window_start=window_start,
            window_end=window_end,
            binding_version=binding_version,
        )
        with _lock(self.lock_path):
            jobs = self._read_jobs()
            existing = next((item for item in jobs if item["idempotency_key"] == key), None)
            if existing is not None:
                return existing, False
            job: dict[str, Any] = {
                "id": (max((item["id"] for item in jobs), default=0) + 1),
                "job_type": "crawl_entity_source",
                "canonical_entity_key": canonical_entity_key,
                "entity_id": entity_id,
                "source": source,
                "capability": capability,
                "domain_key": domain_key,
                "binding_version": binding_version,
                "window_start": window_start.astimezone(UTC).isoformat(),
                "window_end": window_end.astimezone(UTC).isoformat(),
                "freshness_deadline": freshness_deadline.astimezone(UTC).isoformat(),
                "next_run_at": next_run_at.astimezone(UTC).isoformat(),
                "priority": priority,
                "cursor": cursor or {},
                "max_attempts": max_attempts,
                "domain_concurrency_limit": domain_concurrency_limit,
                "idempotency_key": key,
                "status": "queued",
                "attempt_count": 0,
                "lease_owner": None,
                "lease_expires_at": None,
                "billable": True,
                "attempts": [],
            }
            jobs.append(job)
            self._write_jobs(jobs)
            return job, True

    def expire_leases(self, *, now: datetime | None = None) -> int:
        clock = (now or utcnow()).astimezone(UTC)
        with _lock(self.lock_path):
            return self._expire_locked(clock)

    def _expire_locked(self, clock: datetime) -> int:
        jobs = self._read_jobs()
        expired = 0
        for job in jobs:
            expires = job.get("lease_expires_at")
            if job["status"] != "running" or not expires:
                continue
            if datetime.fromisoformat(str(expires)) >= clock:
                continue
            expired += 1
            if int(job["attempt_count"]) >= int(job["max_attempts"]):
                job["status"] = "failed"
            else:
                job["status"] = "queued"
            job["lease_owner"] = None
            job["lease_expires_at"] = None
            for attempt in job["attempts"]:
                if attempt["status"] == "running":
                    attempt["status"] = "lease_expired"
                    attempt["finished_at"] = clock.isoformat()
                    attempt["error_class"] = "LEASE_EXPIRED"
        if expired:
            self._write_jobs(jobs)
        return expired

    def claim(
        self,
        *,
        worker_id: str,
        limit: int = 1,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        clock = (now or utcnow()).astimezone(UTC)
        with _lock(self.lock_path):
            self._expire_locked(clock)
            jobs = self._read_jobs()
            active: dict[str, int] = {}
            ranked: list[RankedJob] = []
            for job in jobs:
                if job["status"] == "running" and job.get("lease_expires_at"):
                    if datetime.fromisoformat(str(job["lease_expires_at"])) >= clock:
                        active[job["domain_key"]] = active.get(job["domain_key"], 0) + 1
                ranked.append(
                    RankedJob(
                        id=int(job["id"]),
                        domain_key=str(job["domain_key"]),
                        priority=int(job["priority"]),
                        freshness_deadline=datetime.fromisoformat(str(job["freshness_deadline"])),
                        next_run_at=datetime.fromisoformat(str(job["next_run_at"])),
                        status=str(job["status"]),
                        domain_concurrency_limit=int(job["domain_concurrency_limit"]),
                    )
                )
            selected = {
                item.id for item in rank_claim_candidates(ranked, now=clock, active_by_domain=active, limit=limit)
            }
            claimed: list[dict[str, Any]] = []
            lease_expires = clock + timedelta(seconds=lease_seconds)
            for job in jobs:
                if job["id"] not in selected:
                    continue
                job["status"] = "running"
                job["lease_owner"] = worker_id
                job["lease_expires_at"] = lease_expires.isoformat()
                job["attempt_count"] = int(job["attempt_count"]) + 1
                attempt = {
                    "id": len(job["attempts"]) + 1,
                    "run_id": f"crawl-{uuid4().hex}",
                    "worker_id": worker_id,
                    "status": "running",
                    "started_at": clock.isoformat(),
                    "lease_expires_at": lease_expires.isoformat(),
                    "cursor": job.get("cursor") or {},
                    "metrics": {},
                }
                job["attempts"].append(attempt)
                claimed.append({**job, "current_attempt": attempt})
                self._append_jsonl(self.attempts_path, {**attempt, "job_id": job["id"]})
            if claimed:
                self._write_jobs(jobs)
            return claimed

    def heartbeat(
        self,
        job_id: int,
        *,
        worker_id: str,
        cursor: dict[str, Any] | None = None,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> bool:
        clock = (now or utcnow()).astimezone(UTC)
        with _lock(self.lock_path):
            jobs = self._read_jobs()
            for job in jobs:
                if int(job["id"]) != job_id:
                    continue
                if job["status"] != "running" or job.get("lease_owner") != worker_id:
                    return False
                job["lease_expires_at"] = (clock + timedelta(seconds=lease_seconds)).isoformat()
                if cursor is not None:
                    job["cursor"] = cursor
                self._write_jobs(jobs)
                return True
            return False

    def finish(
        self,
        job_id: int,
        *,
        worker_id: str,
        outcome: str,
        cursor: dict[str, Any] | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
        metrics: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> bool:
        if outcome not in {"succeeded", "failed", "blocked", "interrupted"}:
            raise ValueError(f"invalid job outcome: {outcome}")
        clock = (now or utcnow()).astimezone(UTC)
        with _lock(self.lock_path):
            jobs = self._read_jobs()
            for job in jobs:
                if int(job["id"]) != job_id:
                    continue
                if job["status"] != "running" or job.get("lease_owner") != worker_id:
                    return False
                if job["status"] in JOB_TERMINALS:
                    return False
                status = outcome
                if outcome == "failed" and int(job["attempt_count"]) < int(job["max_attempts"]):
                    status = "queued"
                if outcome == "interrupted":
                    status = "queued"
                job["status"] = status
                job["lease_owner"] = None
                job["lease_expires_at"] = None
                job["last_outcome"] = outcome
                if cursor is not None:
                    job["cursor"] = cursor
                for attempt in job["attempts"]:
                    if attempt["status"] == "running":
                        attempt["status"] = outcome
                        attempt["finished_at"] = clock.isoformat()
                        attempt["error_class"] = error_class
                        attempt["error_message"] = sanitize_text(error_message) if error_message else None
                        attempt["metrics"] = metrics or {}
                        if cursor is not None:
                            attempt["cursor"] = cursor
                self._write_jobs(jobs)
                return True
            return False

    def inspect(self, job_id: int) -> dict[str, Any] | None:
        with _lock(self.lock_path):
            for job in self._read_jobs():
                if int(job["id"]) == job_id:
                    return job
        return None

    def find_by_idempotency(self, key: str) -> dict[str, Any] | None:
        with _lock(self.lock_path):
            for job in self._read_jobs():
                if job["idempotency_key"] == key:
                    return job
        return None

    def archive_raw(
        self,
        *,
        source: str,
        run_id: str,
        request_scope: str,
        payload: bytes | str,
        url: str,
        http_status: int | None,
        headers: dict[str, Any] | None = None,
        page: int | None = None,
        crawl_job_attempt_id: int | None = None,
        request_succeeded: bool = True,
    ) -> dict[str, Any]:
        path, digest = self.raw.persist(
            source=source,
            run_id=run_id,
            request_scope=request_scope,
            payload=payload,
            provenance={
                "endpoint": url,
                "response_headers": headers or {},
                "authorization": "Bearer secret-token",
            },
            http_status=http_status,
            request_succeeded=request_succeeded,
            page=page,
            crawl_job_attempt_id=crawl_job_attempt_id,
        )
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if "body" in envelope or "payload" in envelope:
            raise RuntimeError("raw envelope must not embed the HTTP body")
        return {
            "envelope_path": str(path),
            "body_sha256": digest,
            "body_uri": envelope["body_uri"],
            "sanitized_url": envelope["sanitized_url"],
            "envelope_sha256": envelope["envelope_sha256"],
        }

    def persist_document(
        self,
        *,
        entity_id: int,
        source: str,
        official_id: str,
        body: bytes,
        official_url: str,
        process_official_id: str,
        crawl_job_attempt_id: int | None = None,
    ) -> dict[str, Any]:
        blob = store_blob(body, raw_root=self.root / "document-blobs")
        with _lock(self.lock_path):
            documents = self._read_documents()
            version = persist_document_metadata(
                documents,
                entity_id=entity_id,
                source=source,
                official_id=official_id,
                sha256=blob.sha256,
                size_bytes=blob.size_bytes,
                body_uri=blob.raw_uri,
                blob_confirmed=True,
                official_url=official_url,
                process_official_id=process_official_id,
                crawl_job_attempt_id=crawl_job_attempt_id,
            )
            self._write_documents(documents)
            return version

    def record_structured_failure(
        self,
        *,
        source: str,
        run_id: str,
        request_scope: str,
        stage: str,
        error: Any,
        http_status: int | None = None,
        url: str | None = None,
        page: int | None = None,
        cursor: str | None = None,
        attempt_no: int = 1,
        job_id: int | None = None,
        crawl_job_attempt_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        classification = classify_failure(http_status=http_status, error=error)
        event = FailureEvent(
            source=source,
            run_id=run_id,
            request_scope=request_scope,
            stage=stage,
            error_class=classification.error_class,
            transient=classification.transient,
            next_action=classification.next_action,
            message=sanitize_text(error),
            url=url,
            http_status=http_status,
            page=page,
            cursor=cursor,
            attempt_no=attempt_no,
            job_id=job_id,
            crawl_job_attempt_id=crawl_job_attempt_id,
            metadata=metadata or {},
        )
        persisted = self.failures.record(event)
        record = event.to_record()
        blob = json.dumps(record)
        if "secret-token" in blob or "password=" in blob:
            raise RuntimeError("structured failure leaked a secret")
        return {**persisted, "event": record}

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
