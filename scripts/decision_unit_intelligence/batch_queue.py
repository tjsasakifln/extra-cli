"""Durable contact-discovery job bus. Additive; does not use crawl_jobs."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

JOB_TYPE = "CONFENGE_CONTACT_DISCOVERY"
CLAIMABLE = ("PENDING", "RETRYABLE")
TERMINAL = ("SUCCEEDED", "BLOCKED", "DLQ", "CANCELLED")
ACTIVE = ("PENDING", "RUNNING", "RETRYABLE")
NOMINAL_BLOCKERS = ("BLOCKED", "DLQ", "CANCELLED")
SNAPSHOT_READY = ("SUCCEEDED",) + NOMINAL_BLOCKERS

ADMISSION_LOCK = "extra:contact_discovery:admission:v1"


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_record(row: Any, description: Any = None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("expected a database row")
    if isinstance(row, Mapping):
        return dict(row)
    if description is not None and isinstance(row, (list, tuple)):
        return {col.name: value for col, value in zip(description, row, strict=False)}
    raise TypeError(f"cannot convert row of type {type(row)!r}")


def fetch_one(cursor: Any) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    return as_record(row, cursor.description)


def fetch_all(cursor: Any) -> list[dict[str, Any]]:
    return [as_record(row, cursor.description) for row in (cursor.fetchall() or [])]


def normalize_account_id(value: str | None) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return digits.zfill(14) if digits else ""


def budget_version_from_knobs(knobs: dict[str, Any]) -> str:
    payload = json.dumps(knobs, sort_keys=True, separators=(",", ":"), default=str)
    return "budget." + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def canonical_payload_hash(payload: Any) -> str:
    """Hash one JSON value with a single cross-writer canonical encoding."""
    # Preserve the escaped-ASCII representation used by production worker
    # outcomes before this helper was centralized. This keeps persisted hashes
    # valid while making every writer and verifier use the same encoding.
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def idempotency_key(
    *,
    cohort_id: str,
    canonical_account_id: str,
    service: str,
    discovery_policy_version: str,
    input_evidence_version: str,
    search_backend: str,
    budget_version: str,
) -> str:
    if not cohort_id.strip():
        raise ValueError("cohort_id is required")
    return _hashed_idempotency_key(
        cohort_id=cohort_id,
        canonical_account_id=canonical_account_id,
        service=service,
        discovery_policy_version=discovery_policy_version,
        input_evidence_version=input_evidence_version,
        search_backend=search_backend,
        budget_version=budget_version,
    )


def _legacy_idempotency_key(
    *,
    canonical_account_id: str,
    service: str,
    discovery_policy_version: str,
    input_evidence_version: str,
    search_backend: str,
    budget_version: str,
) -> str:
    """Match the pre-#468 key only to recognize a replay in its own cohort."""
    return _hashed_idempotency_key(
        cohort_id=None,
        canonical_account_id=canonical_account_id,
        service=service,
        discovery_policy_version=discovery_policy_version,
        input_evidence_version=input_evidence_version,
        search_backend=search_backend,
        budget_version=budget_version,
    )


def _hashed_idempotency_key(
    *,
    cohort_id: str | None,
    canonical_account_id: str,
    service: str,
    discovery_policy_version: str,
    input_evidence_version: str,
    search_backend: str,
    budget_version: str,
) -> str:
    parts = [JOB_TYPE]
    if cohort_id is not None:
        parts.append(cohort_id)
    parts.extend(
        (
            normalize_account_id(canonical_account_id),
            service,
            discovery_policy_version,
            input_evidence_version,
            search_backend,
            budget_version,
        )
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClaimedDiscoveryJob:
    id: int
    cohort_id: str
    canonical_account_id: str
    service: str
    offer_context: str | None
    discovery_policy_version: str
    search_backend: str
    budget_version: str
    code_sha: str
    input_evidence_version: str
    idempotency_key: str
    revision: int
    domain_key: str
    backend_key: str
    cursor: dict[str, Any]
    run_id: str
    attempt_id: int
    attempt_count: int
    max_attempts: int
    cancel_requested: bool


@contextmanager
def connect(dsn: str | None = None):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    resolved = dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("LOCAL_DATALAKE_DSN or DATABASE_URL is required")
    connection = psycopg2.connect(
        resolved,
        cursor_factory=RealDictCursor,
        connect_timeout=10,
    )
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class ContactDiscoveryQueue:
    def __init__(self, connection: Any):
        self.connection = connection

    def cursor(self):
        from psycopg2.extras import RealDictCursor

        return self.connection.cursor(cursor_factory=RealDictCursor)

    def set_kill_switch(self, *, enabled: bool, reason: str, actor: str) -> dict[str, Any]:
        if not reason or not actor:
            raise ValueError("kill switch reason and actor are required")
        with self.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contact_discovery_kill_switch
                SET enabled = %s, reason = %s, changed_by = %s, updated_at = now()
                WHERE singleton
                RETURNING enabled, reason, changed_by, updated_at
                """,
                (enabled, reason, actor),
            )
            row = fetch_one(cursor)
        return row if row else {"enabled": enabled, "reason": reason, "changed_by": actor}

    def kill_switch(self) -> dict[str, Any]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT enabled, reason, changed_by, updated_at FROM contact_discovery_kill_switch WHERE singleton"
            )
            row = fetch_one(cursor)
        return row if row else {"enabled": False, "reason": "", "changed_by": "", "updated_at": None}

    def upsert_cohort(
        self,
        *,
        cohort_id: str,
        service: str,
        offer_context: str | None,
        discovery_policy_version: str,
        search_backend: str,
        budget_version: str,
        code_sha: str,
        input_evidence_version: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO contact_discovery_cohorts (
                    cohort_id, service, offer_context, discovery_policy_version,
                    search_backend, budget_version, code_sha, input_evidence_version,
                    metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (cohort_id) DO UPDATE SET
                    updated_at = now(),
                    metadata = contact_discovery_cohorts.metadata || EXCLUDED.metadata
                WHERE contact_discovery_cohorts.service = EXCLUDED.service
                  AND contact_discovery_cohorts.offer_context IS NOT DISTINCT FROM EXCLUDED.offer_context
                  AND contact_discovery_cohorts.discovery_policy_version = EXCLUDED.discovery_policy_version
                  AND contact_discovery_cohorts.search_backend = EXCLUDED.search_backend
                  AND contact_discovery_cohorts.budget_version = EXCLUDED.budget_version
                  AND contact_discovery_cohorts.code_sha = EXCLUDED.code_sha
                  AND contact_discovery_cohorts.input_evidence_version = EXCLUDED.input_evidence_version
                RETURNING *
                """,
                (
                    cohort_id,
                    service,
                    offer_context,
                    discovery_policy_version,
                    search_backend,
                    budget_version,
                    code_sha,
                    input_evidence_version,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            row = fetch_one(cursor)
            if row is None:
                cursor.execute(
                    "SELECT * FROM contact_discovery_cohorts WHERE cohort_id = %s",
                    (cohort_id,),
                )
                row = fetch_one(cursor)
            if row is None:
                raise RuntimeError("cohort upsert returned no row and no conflicting cohort exists")
            immutable = {
                "service": service,
                "offer_context": offer_context,
                "discovery_policy_version": discovery_policy_version,
                "search_backend": search_backend,
                "budget_version": budget_version,
                "code_sha": code_sha,
                "input_evidence_version": input_evidence_version,
            }
            mismatches = {
                key: {"existing": row.get(key), "requested": expected}
                for key, expected in immutable.items()
                if row.get(key) != expected
            }
            if mismatches:
                raise ValueError(
                    f"cohort {cohort_id} is immutable; use a new cohort id for changed execution contract: "
                    f"{mismatches}"
                )
            return row

    def enqueue(
        self,
        *,
        cohort_id: str,
        canonical_account_id: str,
        service: str,
        offer_context: str | None,
        discovery_policy_version: str,
        search_backend: str,
        budget_version: str,
        code_sha: str,
        input_evidence_version: str,
        priority: int = 0,
        max_attempts: int = 5,
        backend_concurrency_limit: int = 2,
        domain_concurrency_limit: int = 1,
        domain_key: str | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[int, bool]:
        account = normalize_account_id(canonical_account_id)
        if not account:
            raise ValueError("canonical_account_id / CNPJ is required")
        key = idempotency_key(
            cohort_id=cohort_id,
            canonical_account_id=account,
            service=service,
            discovery_policy_version=discovery_policy_version,
            input_evidence_version=input_evidence_version,
            search_backend=search_backend,
            budget_version=budget_version,
        )
        legacy_key = _legacy_idempotency_key(
            canonical_account_id=account,
            service=service,
            discovery_policy_version=discovery_policy_version,
            input_evidence_version=input_evidence_version,
            search_backend=search_backend,
            budget_version=budget_version,
        )
        resolved_domain = domain_key or f"account:{account}"
        with self.cursor() as cursor_handle:
            cursor_handle.execute(
                """
                SELECT id
                FROM contact_discovery_jobs
                WHERE cohort_id = %s AND idempotency_key IN (%s, %s)
                ORDER BY id
                LIMIT 1
                """,
                (cohort_id, key, legacy_key),
            )
            existing = fetch_one(cursor_handle)
            if existing:
                return int(existing["id"]), False
            cursor_handle.execute(
                """
                INSERT INTO contact_discovery_jobs (
                    cohort_id, canonical_account_id, service, offer_context,
                    discovery_policy_version, search_backend, budget_version,
                    code_sha, input_evidence_version, idempotency_key,
                    domain_key, backend_key, cursor, priority, max_attempts,
                    backend_concurrency_limit, domain_concurrency_limit
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s::jsonb, %s, %s,
                    %s, %s
                )
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    cohort_id,
                    account,
                    service,
                    offer_context,
                    discovery_policy_version,
                    search_backend,
                    budget_version,
                    code_sha,
                    input_evidence_version,
                    key,
                    resolved_domain,
                    search_backend,
                    json.dumps(cursor or {}, sort_keys=True),
                    priority,
                    max_attempts,
                    backend_concurrency_limit,
                    domain_concurrency_limit,
                ),
            )
            inserted = fetch_one(cursor_handle)
            if inserted:
                cursor_handle.execute(
                    """
                    UPDATE contact_discovery_cohorts
                    SET denominator = (
                            SELECT COUNT(*) FROM contact_discovery_jobs WHERE cohort_id = %s
                        ),
                        updated_at = now()
                    WHERE cohort_id = %s
                    """,
                    (cohort_id, cohort_id),
                )
                return int(inserted["id"]), True
            cursor_handle.execute(
                "SELECT id FROM contact_discovery_jobs WHERE idempotency_key = %s AND cohort_id = %s",
                (key, cohort_id),
            )
            existing = fetch_one(cursor_handle)
            if not existing:
                raise RuntimeError("contact discovery idempotency lookup failed")
            return int(existing["id"]), False

    def reclaim_expired(self, *, now: datetime | None = None) -> int:
        clock = now or utcnow()
        with self.cursor() as cursor:
            cursor.execute(
                """
                WITH expired AS (
                    UPDATE contact_discovery_jobs
                    SET status = CASE
                            WHEN cancel_requested THEN 'CANCELLED'
                            WHEN attempt_count >= max_attempts THEN 'DLQ'
                            ELSE 'RETRYABLE'
                        END,
                        next_run_at = CASE
                            WHEN cancel_requested THEN now()
                            WHEN attempt_count >= max_attempts THEN now() + interval '24 hours'
                            ELSE now()
                        END,
                        last_outcome = 'lease_expired',
                        last_reason_code = 'LEASE_EXPIRED',
                        last_error = 'worker lease expired before terminal result',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        updated_at = now()
                    WHERE status = 'RUNNING'
                      AND lease_expires_at < %s
                    RETURNING id, status, attempt_count, max_attempts, cursor
                )
                UPDATE contact_discovery_attempts a
                SET status = 'LEASE_EXPIRED', finished_at = %s,
                    reason_code = 'LEASE_EXPIRED',
                    error_message = 'worker lease expired before terminal result'
                FROM expired e
                WHERE a.job_id = e.id AND a.status = 'RUNNING'
                """,
                (clock, clock),
            )
            return int(cursor.rowcount or 0)

    def claim(
        self,
        *,
        worker_id: str,
        limit: int = 1,
        lease_seconds: int = 300,
        now: datetime | None = None,
        backend_filter: str | None = None,
    ) -> list[ClaimedDiscoveryJob]:
        if limit < 1 or lease_seconds < 1:
            raise ValueError("claim limit and lease_seconds must be positive")
        clock = now
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (ADMISSION_LOCK,),
            )
            if clock is None:
                # Jobs are admitted with PostgreSQL's NOW() default. Anchor an
                # ordinary claim to that same clock so small host/DB skew
                # cannot make a freshly inserted job appear scheduled in the
                # future. Explicit `now=` remains available for deterministic
                # recovery tests.
                cursor.execute("SELECT clock_timestamp() AS clock")
                clock_row = fetch_one(cursor)
                clock = clock_row["clock"] if clock_row else utcnow()
            lease_expires = clock + timedelta(seconds=lease_seconds)
            switch = self.kill_switch()
            if switch.get("enabled"):
                self.connection.commit()
                return []
            self.reclaim_expired(now=clock)
            backend_clause = ""
            params: list[Any] = [clock, clock, clock, clock]
            if backend_filter:
                backend_clause = "AND candidate.backend_key = %s"
                params.append(backend_filter)
            params.extend([limit, worker_id, lease_expires, clock, clock])
            cursor.execute(  # noqa: S608 - backend_clause is a static SQL fragment
                f"""
                WITH open_circuits AS MATERIALIZED (
                    SELECT backend_key
                    FROM contact_discovery_backend_circuit
                    WHERE state = 'open'
                      AND cooldown_until IS NOT NULL
                      AND cooldown_until > %s
                ),
                active_backends AS MATERIALIZED (
                    SELECT backend_key, COUNT(*) AS active_count
                    FROM contact_discovery_jobs
                    WHERE status = 'RUNNING'
                      AND lease_expires_at >= %s
                    GROUP BY backend_key
                ),
                active_domains AS MATERIALIZED (
                    SELECT domain_key, COUNT(*) AS active_count
                    FROM contact_discovery_jobs
                    WHERE status = 'RUNNING'
                      AND lease_expires_at >= %s
                    GROUP BY domain_key
                ),
                ranked AS MATERIALIZED (
                    SELECT candidate.id,
                           candidate.priority,
                           candidate.next_run_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY candidate.backend_key
                               ORDER BY candidate.priority DESC, candidate.next_run_at ASC, candidate.id ASC
                           ) AS backend_slot,
                           ROW_NUMBER() OVER (
                               PARTITION BY candidate.domain_key
                               ORDER BY candidate.priority DESC, candidate.next_run_at ASC, candidate.id ASC
                           ) AS domain_slot,
                           GREATEST(
                               candidate.backend_concurrency_limit
                               - COALESCE(active_backend.active_count, 0),
                               0
                           ) AS backend_available,
                           GREATEST(
                               candidate.domain_concurrency_limit
                               - COALESCE(active_domain.active_count, 0),
                               0
                           ) AS domain_available
                    FROM contact_discovery_jobs candidate
                    LEFT JOIN active_backends active_backend USING (backend_key)
                    LEFT JOIN active_domains active_domain USING (domain_key)
                    LEFT JOIN open_circuits circuit USING (backend_key)
                    WHERE candidate.status IN ('PENDING', 'RETRYABLE')
                      AND candidate.next_run_at <= %s
                      AND candidate.cancel_requested = FALSE
                      AND circuit.backend_key IS NULL
                      {backend_clause}
                ),
                candidates AS MATERIALIZED (
                    SELECT candidate.id
                    FROM contact_discovery_jobs candidate
                    JOIN ranked ON ranked.id = candidate.id
                    WHERE ranked.backend_slot <= ranked.backend_available
                      AND ranked.domain_slot <= ranked.domain_available
                    ORDER BY ranked.priority DESC, ranked.next_run_at ASC, ranked.id ASC
                    LIMIT %s
                    FOR UPDATE OF candidate SKIP LOCKED
                )
                UPDATE contact_discovery_jobs job
                SET status = 'RUNNING', lease_owner = %s,
                    lease_expires_at = %s, heartbeat_at = %s,
                    attempt_count = job.attempt_count + 1,
                    updated_at = %s
                FROM candidates
                WHERE job.id = candidates.id
                RETURNING job.*
                """,  # noqa: S608
                params,
            )
            rows = fetch_all(cursor)
            claimed: list[ClaimedDiscoveryJob] = []
            for row in rows:
                run_id = f"cd-{uuid.uuid4().hex}"
                cursor.execute(
                    """
                    INSERT INTO contact_discovery_attempts (
                        job_id, run_id, worker_id, status, started_at,
                        heartbeat_at, lease_expires_at, cursor, metrics
                    ) VALUES (%s, %s, %s, 'RUNNING', %s, %s, %s, %s::jsonb, '{}'::jsonb)
                    RETURNING id
                    """,
                    (
                        row["id"],
                        run_id,
                        worker_id,
                        clock,
                        clock,
                        lease_expires,
                        json.dumps(row.get("cursor") or {}, sort_keys=True),
                    ),
                )
                attempt = fetch_one(cursor)
                if attempt is None:
                    raise RuntimeError("attempt insert returned no row")
                claimed.append(
                    ClaimedDiscoveryJob(
                        id=int(row["id"]),
                        cohort_id=str(row["cohort_id"]),
                        canonical_account_id=str(row["canonical_account_id"]),
                        service=str(row["service"]),
                        offer_context=row.get("offer_context"),
                        discovery_policy_version=str(row["discovery_policy_version"]),
                        search_backend=str(row["search_backend"]),
                        budget_version=str(row["budget_version"]),
                        code_sha=str(row["code_sha"]),
                        input_evidence_version=str(row["input_evidence_version"]),
                        idempotency_key=str(row["idempotency_key"]),
                        revision=int(row["revision"]),
                        domain_key=str(row["domain_key"]),
                        backend_key=str(row["backend_key"]),
                        cursor=dict(row.get("cursor") or {}),
                        run_id=run_id,
                        attempt_id=int(attempt["id"]),
                        attempt_count=int(row["attempt_count"]),
                        max_attempts=int(row["max_attempts"]),
                        cancel_requested=bool(row.get("cancel_requested")),
                    )
                )
            self.connection.commit()
            return claimed

    def heartbeat(
        self,
        job: ClaimedDiscoveryJob,
        *,
        worker_id: str,
        cursor_state: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        lease_seconds: int = 300,
    ) -> bool:
        clock = utcnow()
        lease_expires = clock + timedelta(seconds=lease_seconds)
        with self.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contact_discovery_jobs
                SET heartbeat_at = %s, lease_expires_at = %s,
                    cursor = %s::jsonb, updated_at = %s
                WHERE id = %s AND status = 'RUNNING' AND lease_owner = %s
                RETURNING cancel_requested
                """,
                (
                    clock,
                    lease_expires,
                    json.dumps(cursor_state if cursor_state is not None else job.cursor),
                    clock,
                    job.id,
                    worker_id,
                ),
            )
            row = fetch_one(cursor)
            if not row:
                return False
            cursor.execute(
                """
                UPDATE contact_discovery_attempts
                SET heartbeat_at = %s, lease_expires_at = %s,
                    cursor = %s::jsonb,
                    metrics = metrics || %s::jsonb
                WHERE id = %s AND status = 'RUNNING'
                """,
                (
                    clock,
                    lease_expires,
                    json.dumps(cursor_state if cursor_state is not None else job.cursor),
                    json.dumps(metrics or {}),
                    job.attempt_id,
                ),
            )
            return True

    def finish(
        self,
        job: ClaimedDiscoveryJob,
        *,
        worker_id: str,
        outcome: str,
        reason_code: str,
        next_run_at: datetime | None = None,
        cursor_state: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error_message: str | None = None,
        output_pointer: str | None = None,
        output_hash: str | None = None,
        domain_key: str | None = None,
    ) -> bool:
        if outcome not in {"SUCCEEDED", "BLOCKED", "RETRYABLE", "DLQ", "CANCELLED", "INTERRUPTED"}:
            raise ValueError(f"invalid contact discovery outcome: {outcome}")
        if reason_code in {"SEM_CONTATO", "NO_CONTACT", "NO_CONTACT_FOUND", "sem contato encontrado"}:
            raise ValueError("forbidden reason code; timeout/budget/block must stay explicit")

        job_status = outcome
        if outcome == "INTERRUPTED":
            job_status = "RETRYABLE"
        if outcome == "RETRYABLE" and job.attempt_count >= job.max_attempts:
            job_status = "DLQ"
            outcome = "DLQ"
        clock = utcnow()
        delay = next_run_at or clock
        cursor_payload = cursor_state if cursor_state is not None else job.cursor
        metrics_payload = metrics or {}

        with self.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contact_discovery_jobs
                SET status = %s, next_run_at = %s,
                    cursor = %s::jsonb, last_outcome = %s,
                    last_reason_code = %s, last_error = %s,
                    output_pointer = COALESCE(%s, output_pointer),
                    output_hash = COALESCE(%s, output_hash),
                    cost_metrics = cost_metrics || %s::jsonb,
                    domain_key = COALESCE(%s, domain_key),
                    lease_owner = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL, updated_at = %s
                WHERE id = %s AND status = 'RUNNING' AND lease_owner = %s
                """,
                (
                    job_status,
                    delay,
                    json.dumps(cursor_payload, sort_keys=True),
                    outcome,
                    reason_code,
                    error_message,
                    output_pointer,
                    output_hash,
                    json.dumps(metrics_payload),
                    domain_key,
                    clock,
                    job.id,
                    worker_id,
                ),
            )
            owned = cursor.rowcount == 1
            if owned:
                cursor.execute(
                    """
                    UPDATE contact_discovery_attempts
                    SET status = %s, finished_at = %s, heartbeat_at = %s,
                        cursor = %s::jsonb, metrics = metrics || %s::jsonb,
                        reason_code = %s, error_message = %s,
                        output_pointer = COALESCE(%s, output_pointer),
                        output_hash = COALESCE(%s, output_hash)
                    WHERE id = %s AND status = 'RUNNING'
                    """,
                    (
                        outcome if outcome != "INTERRUPTED" else "INTERRUPTED",
                        clock,
                        clock,
                        json.dumps(cursor_payload, sort_keys=True),
                        json.dumps(metrics_payload),
                        reason_code,
                        error_message,
                        output_pointer,
                        output_hash,
                        job.attempt_id,
                    ),
                )
                if job_status == "RETRYABLE":
                    self._record_backend_failure(cursor, job.backend_key, reason_code)
                elif job_status == "SUCCEEDED":
                    self._record_backend_success(cursor, job.backend_key)
                return True

            cursor.execute(
                """
                SELECT status, output_hash, last_reason_code
                FROM contact_discovery_jobs
                WHERE id = %s
                """,
                (job.id,),
            )
            existing = fetch_one(cursor)
            if not existing:
                return False
            same_truth = (
                existing["status"] in TERMINAL
                and existing["output_hash"]
                and output_hash
                and existing["output_hash"] == output_hash
            )
            if same_truth:
                cursor.execute(
                    """
                    UPDATE contact_discovery_attempts
                    SET status = CASE WHEN status = 'RUNNING' THEN %s ELSE status END,
                        finished_at = COALESCE(finished_at, %s),
                        heartbeat_at = %s,
                        reason_code = COALESCE(reason_code, %s),
                        output_pointer = COALESCE(output_pointer, %s),
                        output_hash = COALESCE(output_hash, %s)
                    WHERE id = %s
                    """,
                    (existing["status"], clock, clock, reason_code, output_pointer, output_hash, job.attempt_id),
                )
                return True
            return False

    def _record_backend_failure(self, cursor: Any, backend_key: str, reason_code: str) -> None:
        if reason_code not in {"PROVIDER_429", "PROVIDER_5XX", "PROVIDER_TIMEOUT"}:
            return
        cursor.execute(
            """
            INSERT INTO contact_discovery_backend_circuit (
                backend_key, state, consecutive_failures, last_error_class, updated_at
            ) VALUES (%s, 'closed', 1, %s, now())
            ON CONFLICT (backend_key) DO UPDATE SET
                consecutive_failures = contact_discovery_backend_circuit.consecutive_failures + 1,
                last_error_class = EXCLUDED.last_error_class,
                state = CASE
                    WHEN contact_discovery_backend_circuit.consecutive_failures + 1 >= 3
                    THEN 'open' ELSE contact_discovery_backend_circuit.state
                END,
                opened_at = CASE
                    WHEN contact_discovery_backend_circuit.consecutive_failures + 1 >= 3
                    THEN now() ELSE contact_discovery_backend_circuit.opened_at
                END,
                cooldown_until = CASE
                    WHEN contact_discovery_backend_circuit.consecutive_failures + 1 >= 3
                    THEN now() + interval '5 minutes'
                    ELSE contact_discovery_backend_circuit.cooldown_until
                END,
                updated_at = now()
            """,
            (backend_key, reason_code),
        )

    def _record_backend_success(self, cursor: Any, backend_key: str) -> None:
        cursor.execute(
            """
            INSERT INTO contact_discovery_backend_circuit (
                backend_key, state, consecutive_failures, updated_at
            ) VALUES (%s, 'closed', 0, now())
            ON CONFLICT (backend_key) DO UPDATE SET
                state = 'closed',
                consecutive_failures = 0,
                opened_at = NULL,
                cooldown_until = NULL,
                updated_at = now()
            """,
            (backend_key,),
        )

    def request_cancel(self, *, cohort_id: str | None = None, job_id: int | None = None) -> int:
        clauses = ["status IN ('PENDING', 'RETRYABLE', 'RUNNING')"]
        params: list[Any] = []
        if cohort_id:
            clauses.append("cohort_id = %s")
            params.append(cohort_id)
        if job_id is not None:
            clauses.append("id = %s")
            params.append(job_id)
        if not cohort_id and job_id is None:
            raise ValueError("cancel requires cohort_id or job_id")
        where = " AND ".join(clauses)
        with self.cursor() as cursor:
            cursor.execute(  # noqa: S608 - WHERE is composed of fixed clauses
                f"""
                UPDATE contact_discovery_jobs
                SET cancel_requested = TRUE,
                    status = CASE WHEN status IN ('PENDING', 'RETRYABLE') THEN 'CANCELLED' ELSE status END,
                    last_outcome = CASE
                        WHEN status IN ('PENDING', 'RETRYABLE') THEN 'cancelled' ELSE last_outcome
                    END,
                    last_reason_code = CASE
                        WHEN status IN ('PENDING', 'RETRYABLE') THEN 'CANCELLED' ELSE last_reason_code
                    END,
                    lease_owner = CASE
                        WHEN status IN ('PENDING', 'RETRYABLE') THEN NULL ELSE lease_owner
                    END,
                    updated_at = now()
                WHERE {where}
                """,  # noqa: S608
                params,
            )
            return int(cursor.rowcount or 0)

    def retry(
        self,
        *,
        cohort_id: str | None = None,
        job_id: int | None = None,
        reason_codes: list[str] | None = None,
    ) -> int:
        clauses = ["status IN ('RETRYABLE', 'BLOCKED', 'DLQ')"]
        params: list[Any] = []
        if cohort_id:
            clauses.append("cohort_id = %s")
            params.append(cohort_id)
        if job_id is not None:
            clauses.append("id = %s")
            params.append(job_id)
        if reason_codes:
            clauses.append("last_reason_code = ANY(%s)")
            params.append(reason_codes)
        if not cohort_id and job_id is None:
            raise ValueError("retry requires cohort_id or job_id")
        where = " AND ".join(clauses)
        with self.cursor() as cursor:
            cursor.execute(  # noqa: S608 - WHERE is composed of fixed clauses
                f"""
                UPDATE contact_discovery_jobs
                SET status = 'PENDING',
                    next_run_at = now(),
                    cancel_requested = FALSE,
                    last_outcome = 'requeued',
                    updated_at = now()
                WHERE {where}
                """,  # noqa: S608
                params,
            )
            return int(cursor.rowcount or 0)

    def resume(self, *, cohort_id: str) -> dict[str, Any]:
        reclaimed = self.reclaim_expired()
        retried = self.retry(cohort_id=cohort_id)
        with self.cursor() as cursor:
            cursor.execute(
                """
                UPDATE contact_discovery_jobs
                SET next_run_at = now(), updated_at = now()
                WHERE cohort_id = %s AND status IN ('PENDING', 'RETRYABLE')
                """,
                (cohort_id,),
            )
            pending = int(cursor.rowcount or 0)
        return {"reclaimed": reclaimed, "retried": retried, "pending": pending}

    def inspect(self, *, cohort_id: str | None = None, job_id: int | None = None) -> list[dict[str, Any]]:
        clauses = ["TRUE"]
        params: list[Any] = []
        if cohort_id:
            clauses.append("cohort_id = %s")
            params.append(cohort_id)
        if job_id is not None:
            clauses.append("id = %s")
            params.append(job_id)
        where = " AND ".join(clauses)
        with self.cursor() as cursor:
            cursor.execute(  # noqa: S608 - WHERE is composed of fixed clauses
                f"""
                SELECT id, cohort_id, canonical_account_id, status, revision,
                       last_reason_code, last_outcome, last_error, attempt_count,
                       max_attempts, output_pointer, output_hash, lease_owner,
                       lease_expires_at, heartbeat_at, next_run_at,
                       discovery_policy_version, search_backend, budget_version,
                       code_sha, input_evidence_version, idempotency_key,
                       cost_metrics, domain_key, backend_key, cancel_requested,
                       priority, cursor
                FROM contact_discovery_jobs
                WHERE {where}
                ORDER BY id
                """,  # noqa: S608
                params,
            )
            return fetch_all(cursor)

    def failures(self, *, cohort_id: str) -> list[dict[str, Any]]:
        with self.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, canonical_account_id, status, last_reason_code,
                       last_error, attempt_count, output_pointer, output_hash
                FROM contact_discovery_jobs
                WHERE cohort_id = %s
                  AND status IN ('BLOCKED', 'RETRYABLE', 'DLQ')
                ORDER BY id
                """,
                (cohort_id,),
            )
            return fetch_all(cursor)

    def progress(self, *, cohort_id: str) -> dict[str, Any]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM contact_discovery_cohorts WHERE cohort_id = %s",
                (cohort_id,),
            )
            cohort = fetch_one(cursor)
            if not cohort:
                raise ValueError(f"unknown cohort: {cohort_id}")
            cursor.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM contact_discovery_jobs
                WHERE cohort_id = %s
                GROUP BY status
                """,
                (cohort_id,),
            )
            counts = {str(row["status"]): int(row["n"]) for row in fetch_all(cursor)}
            cursor.execute(
                """
                SELECT last_reason_code, COUNT(*) AS n
                FROM contact_discovery_jobs
                WHERE cohort_id = %s AND last_reason_code IS NOT NULL
                GROUP BY last_reason_code
                """,
                (cohort_id,),
            )
            reasons = {str(row["last_reason_code"]): int(row["n"]) for row in fetch_all(cursor)}
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'SUCCEEDED') AS succeeded,
                    COALESCE(SUM((cost_metrics->>'duration_ms')::numeric), 0) AS duration_ms,
                    COALESCE(SUM((cost_metrics->>'searches')::numeric), 0) AS searches,
                    COALESCE(SUM((cost_metrics->>'pages')::numeric), 0) AS pages,
                    COALESCE(SUM((cost_metrics->>'bytes_touched')::numeric), 0) AS bytes_touched,
                    COALESCE(SUM((cost_metrics->>'cache_hits')::numeric), 0) AS cache_hits,
                    COALESCE(SUM((cost_metrics->>'cache_misses')::numeric), 0) AS cache_misses,
                    COALESCE(SUM((cost_metrics->>'external_cost_brl')::numeric), 0) AS external_cost_brl,
                    COALESCE(SUM((cost_metrics->>'domains_resolved')::numeric), 0) AS domains_resolved,
                    COALESCE(SUM((cost_metrics->>'named_people')::numeric), 0) AS named_people,
                    COALESCE(SUM((cost_metrics->>'observed_direct_email')::numeric), 0) AS observed_direct_email,
                    COALESCE(SUM((cost_metrics->>'inferred_email')::numeric), 0) AS inferred_email,
                    COALESCE(SUM((cost_metrics->>'email_validated')::numeric), 0) AS email_validated,
                    COALESCE(SUM((cost_metrics->>'retries')::numeric), 0) AS retries,
                    COALESCE(SUM((cost_metrics->>'provider_failures')::numeric), 0) AS provider_failures
                FROM contact_discovery_jobs
                WHERE cohort_id = %s
                """,
                (cohort_id,),
            )
            totals = fetch_one(cursor) or {}
            cursor.execute(
                """
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (
                        ORDER BY (cost_metrics->>'duration_ms')::numeric
                    ) AS p50_ms,
                    percentile_cont(0.95) WITHIN GROUP (
                        ORDER BY (cost_metrics->>'duration_ms')::numeric
                    ) AS p95_ms
                FROM contact_discovery_jobs
                WHERE cohort_id = %s
                  AND cost_metrics ? 'duration_ms'
                """,
                (cohort_id,),
            )
            latency = fetch_one(cursor) or {}
            cursor.execute(
                """
                SELECT MIN(created_at) AS first_at, MAX(updated_at) AS last_at
                FROM contact_discovery_jobs
                WHERE cohort_id = %s
                """,
                (cohort_id,),
            )
            window = fetch_one(cursor) or {}
        denominator = int(cohort["denominator"] or sum(counts.values()))
        succeeded = int(counts.get("SUCCEEDED") or 0)
        first_at = window.get("first_at")
        last_at = window.get("last_at")
        hours = 0.0
        if first_at and last_at:
            hours = max((last_at - first_at).total_seconds() / 3600.0, 1e-9)
        cache_hits = float(totals.get("cache_hits") or 0)
        cache_misses = float(totals.get("cache_misses") or 0)
        population_contract = cohort.get("metadata")
        if not isinstance(population_contract, dict):
            population_contract = {}
        return {
            "cohort_id": cohort_id,
            "job_type": JOB_TYPE,
            "status": cohort["status"],
            "denominator": denominator,
            "counts": {
                "pending": int(counts.get("PENDING") or 0),
                "running": int(counts.get("RUNNING") or 0),
                "succeeded": succeeded,
                "blocked": int(counts.get("BLOCKED") or 0),
                "retryable": int(counts.get("RETRYABLE") or 0),
                "dlq": int(counts.get("DLQ") or 0),
                "cancelled": int(counts.get("CANCELLED") or 0),
            },
            "reason_codes": reasons,
            "throughput_accounts_per_hour": round(succeeded / hours, 4) if succeeded else 0.0,
            "p50_ms": float(latency["p50_ms"]) if latency.get("p50_ms") is not None else None,
            "p95_ms": float(latency["p95_ms"]) if latency.get("p95_ms") is not None else None,
            "searches": float(totals.get("searches") or 0),
            "pages": float(totals.get("pages") or 0),
            "bytes_touched": float(totals.get("bytes_touched") or 0),
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / (cache_hits + cache_misses), 4)
            if cache_hits + cache_misses
            else 0.0,
            "external_cost_brl": float(totals.get("external_cost_brl") or 0),
            "domains_resolved": float(totals.get("domains_resolved") or 0),
            "named_people": float(totals.get("named_people") or 0),
            "observed_direct_email": float(totals.get("observed_direct_email") or 0),
            "inferred_email": float(totals.get("inferred_email") or 0),
            "email_validated": float(totals.get("email_validated") or 0),
            "retries": float(totals.get("retries") or 0),
            "provider_failures": float(totals.get("provider_failures") or 0),
            "policy_version": cohort["discovery_policy_version"],
            "search_backend": cohort["search_backend"],
            "budget_version": cohort["budget_version"],
            "code_sha": cohort["code_sha"],
            "input_evidence_version": cohort["input_evidence_version"],
            "population_contract": population_contract,
            "snapshot_id": cohort.get("snapshot_id"),
            "snapshot_hash": cohort.get("snapshot_hash"),
            "closable": self._closable(denominator, counts),
        }

    def _closable(self, denominator: int, counts: dict[str, int]) -> bool:
        total = sum(counts.values())
        if denominator <= 0 or total != denominator:
            return False
        open_count = int(counts.get("PENDING") or 0) + int(counts.get("RUNNING") or 0) + int(
            counts.get("RETRYABLE") or 0
        )
        return open_count == 0

    def duplicate_identities(self, *, cohort_id: str) -> list[dict[str, Any]]:
        with self.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_account_id, discovery_policy_version,
                       input_evidence_version, search_backend, budget_version,
                       service, COUNT(*) AS n
                FROM contact_discovery_jobs
                WHERE cohort_id = %s
                GROUP BY 1, 2, 3, 4, 5, 6
                HAVING COUNT(*) > 1
                """,
                (cohort_id,),
            )
            return fetch_all(cursor)

    def mark_cohort_published(
        self,
        *,
        cohort_id: str,
        snapshot_id: str,
        pointer: str,
        content_hash: str,
        approved: bool,
        status_counts: dict[str, Any],
        reject_reason: str | None,
    ) -> None:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM contact_discovery_cohorts WHERE cohort_id = %s",
                (cohort_id,),
            )
            cohort = fetch_one(cursor)
            if not cohort:
                raise ValueError(f"unknown cohort: {cohort_id}")
            cursor.execute(
                """
                INSERT INTO contact_discovery_snapshots (
                    snapshot_id, cohort_id, approved, pointer, content_hash,
                    denominator, status_counts, policy_version, code_sha,
                    search_backend, budget_version, reject_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot_id,
                    cohort_id,
                    approved,
                    pointer,
                    content_hash,
                    int(cohort["denominator"] or 0),
                    json.dumps(status_counts, sort_keys=True),
                    cohort["discovery_policy_version"],
                    cohort["code_sha"],
                    cohort["search_backend"],
                    cohort["budget_version"],
                    reject_reason,
                ),
            )
            if approved:
                cursor.execute(
                    """
                    UPDATE contact_discovery_cohorts
                    SET status = 'PUBLISHED',
                        snapshot_id = %s,
                        snapshot_pointer = %s,
                        snapshot_hash = %s,
                        published_at = now(),
                        updated_at = now()
                    WHERE cohort_id = %s
                    """,
                    (snapshot_id, pointer, content_hash, cohort_id),
                )
