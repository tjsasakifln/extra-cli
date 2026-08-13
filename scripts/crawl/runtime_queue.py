"""PostgreSQL-backed crawl queue with transactional leases and restart recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_idempotency_key(
    *,
    canonical_entity_key: str,
    source: str,
    capability: str,
    window_start: datetime,
    window_end: datetime,
    binding_version: str,
) -> str:
    canonical = "|".join(
        (
            canonical_entity_key,
            source,
            capability,
            window_start.astimezone(UTC).isoformat(),
            window_end.astimezone(UTC).isoformat(),
            binding_version,
        )
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    canonical_entity_key: str
    entity_id: int
    source: str
    capability: str
    domain_key: str
    binding_version: str
    window_start: datetime
    window_end: datetime
    cursor: dict[str, Any]
    freshness_deadline: datetime
    run_id: str
    attempt_id: int
    attempt_count: int
    max_attempts: int


def connect(dsn: str | None = None) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    resolved = dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("LOCAL_DATALAKE_DSN or DATABASE_URL is required")
    return psycopg2.connect(resolved, cursor_factory=RealDictCursor)


class CrawlQueue:
    def __init__(self, connection: Any):
        self.connection = connection

    def enqueue(
        self,
        *,
        entity_id: int,
        canonical_entity_key: str | None = None,
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
        idempotency_key: str | None = None,
    ) -> tuple[int, bool]:
        canonical_key = canonical_entity_key or f"db:{entity_id}"
        key = idempotency_key or canonical_idempotency_key(
            canonical_entity_key=canonical_key,
            source=source,
            capability=capability,
            window_start=window_start,
            window_end=window_end,
            binding_version=binding_version,
        )
        with self.connection.cursor() as cursor_handle:
            cursor_handle.execute(
                """
                INSERT INTO crawl_jobs (
                    canonical_entity_key, entity_id, source, capability, domain_key, binding_version,
                    window_start, window_end, freshness_deadline, next_run_at,
                    priority, cursor, max_attempts, domain_concurrency_limit,
                    idempotency_key
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s::jsonb, %s, %s, %s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
                """,
                (
                    canonical_key,
                    entity_id,
                    source,
                    capability,
                    domain_key,
                    binding_version,
                    window_start,
                    window_end,
                    freshness_deadline,
                    next_run_at,
                    priority,
                    json.dumps(cursor or {}, sort_keys=True),
                    max_attempts,
                    domain_concurrency_limit,
                    key,
                ),
            )
            inserted = cursor_handle.fetchone()
            if inserted:
                return int(inserted["id"]), True
            cursor_handle.execute(
                "SELECT id FROM crawl_jobs WHERE idempotency_key = %s",
                (key,),
            )
            existing = cursor_handle.fetchone()
            if not existing:
                raise RuntimeError("crawl queue idempotency lookup failed")
            return int(existing["id"]), False

    def reclaim_expired(self, *, now: datetime | None = None) -> int:
        clock = now or utcnow()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                WITH expired AS (
                    UPDATE crawl_jobs
                    SET status = CASE
                            WHEN attempt_count >= max_attempts THEN 'failed'
                            ELSE 'queued'
                        END,
                        next_run_at = CASE
                            WHEN attempt_count >= max_attempts THEN now() + interval '24 hours'
                            ELSE now()
                        END,
                        last_outcome = 'lease_expired',
                        last_error_class = 'LEASE_EXPIRED',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        updated_at = now()
                    WHERE status = 'running'
                      AND lease_expires_at < %s
                    RETURNING id
                )
                UPDATE crawl_job_attempts a
                SET status = 'lease_expired', finished_at = %s,
                    error_class = 'LEASE_EXPIRED',
                    error_message = 'worker lease expired before terminal result'
                FROM expired e
                WHERE a.job_id = e.id AND a.status = 'running'
                """,
                (clock, clock),
            )
            return cursor.rowcount or 0

    def claim(
        self,
        *,
        worker_id: str,
        limit: int = 1,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> list[ClaimedJob]:
        if limit < 1 or lease_seconds < 1:
            raise ValueError("claim limit and lease_seconds must be positive")
        clock = now or utcnow()
        self.reclaim_expired(now=clock)
        lease_expires = clock + timedelta(seconds=lease_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                WITH candidates AS (
                    SELECT candidate.id
                    FROM crawl_jobs candidate
                    WHERE candidate.status = 'queued'
                      AND candidate.next_run_at <= %s
                      AND pg_try_advisory_xact_lock(hashtext(candidate.domain_key))
                      AND NOT EXISTS (
                          SELECT 1
                          FROM crawl_jobs active
                          WHERE active.status = 'running'
                            AND active.domain_key = candidate.domain_key
                            AND active.lease_expires_at >= %s
                          GROUP BY active.domain_key
                          HAVING COUNT(*) >= candidate.domain_concurrency_limit
                      )
                    ORDER BY candidate.priority DESC,
                             candidate.freshness_deadline ASC,
                             candidate.next_run_at ASC,
                             candidate.id ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE crawl_jobs job
                SET status = 'running', lease_owner = %s,
                    lease_expires_at = %s, heartbeat_at = %s,
                    attempt_count = job.attempt_count + 1,
                    updated_at = %s
                FROM candidates
                WHERE job.id = candidates.id
                RETURNING job.*
                """,
                (clock, clock, limit, worker_id, lease_expires, clock, clock),
            )
            rows = list(cursor.fetchall() or [])
            claimed: list[ClaimedJob] = []
            for row in rows:
                run_id = f"crawl-{uuid.uuid4().hex}"
                cursor.execute(
                    """
                    INSERT INTO crawl_job_attempts (
                        job_id, run_id, worker_id, status, started_at,
                        heartbeat_at, lease_expires_at, cursor, metrics
                    ) VALUES (%s, %s, %s, 'running', %s, %s, %s, %s::jsonb, '{}'::jsonb)
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
                attempt = cursor.fetchone()
                claimed.append(
                    ClaimedJob(
                        id=int(row["id"]),
                        canonical_entity_key=str(row["canonical_entity_key"]),
                        entity_id=int(row["entity_id"]),
                        source=str(row["source"]),
                        capability=str(row["capability"]),
                        domain_key=str(row["domain_key"]),
                        binding_version=str(row["binding_version"]),
                        window_start=row["window_start"],
                        window_end=row["window_end"],
                        cursor=dict(row.get("cursor") or {}),
                        freshness_deadline=row["freshness_deadline"],
                        run_id=run_id,
                        attempt_id=int(attempt["id"]),
                        attempt_count=int(row["attempt_count"]),
                        max_attempts=int(row["max_attempts"]),
                    )
                )
            return claimed

    def heartbeat(
        self,
        job: ClaimedJob,
        *,
        worker_id: str,
        cursor_state: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        lease_seconds: int = 300,
    ) -> bool:
        clock = utcnow()
        lease_expires = clock + timedelta(seconds=lease_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE crawl_jobs
                SET heartbeat_at = %s, lease_expires_at = %s,
                    cursor = %s::jsonb, updated_at = %s
                WHERE id = %s AND status = 'running' AND lease_owner = %s
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
            owned = cursor.rowcount == 1
            if owned:
                cursor.execute(
                    """
                    UPDATE crawl_job_attempts
                    SET heartbeat_at = %s, lease_expires_at = %s,
                        cursor = %s::jsonb,
                        metrics = metrics || %s::jsonb
                    WHERE id = %s AND status = 'running'
                    """,
                    (
                        clock,
                        lease_expires,
                        json.dumps(cursor_state if cursor_state is not None else job.cursor),
                        json.dumps(metrics or {}),
                        job.attempt_id,
                    ),
                )
            return owned

    def finish(
        self,
        job: ClaimedJob,
        *,
        worker_id: str,
        outcome: str,
        next_run_at: datetime,
        cursor_state: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        if outcome not in {"succeeded", "failed", "blocked", "interrupted"}:
            raise ValueError(f"invalid crawl job outcome: {outcome}")
        job_status = "queued" if outcome == "succeeded" else outcome
        if outcome == "failed" and job.attempt_count < job.max_attempts:
            job_status = "queued"
        if outcome == "interrupted":
            job_status = "queued"
        clock = utcnow()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE crawl_jobs
                SET status = %s, next_run_at = %s,
                    cursor = %s::jsonb, last_outcome = %s,
                    last_error_class = %s, last_error = %s,
                    lease_owner = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL, updated_at = %s
                WHERE id = %s AND status = 'running' AND lease_owner = %s
                """,
                (
                    job_status,
                    next_run_at,
                    json.dumps(cursor_state if cursor_state is not None else job.cursor),
                    outcome,
                    error_class,
                    error_message,
                    clock,
                    job.id,
                    worker_id,
                ),
            )
            owned = cursor.rowcount == 1
            if not owned:
                return False
            cursor.execute(
                """
                UPDATE crawl_job_attempts
                SET status = %s, finished_at = %s, heartbeat_at = %s,
                    cursor = %s::jsonb, metrics = metrics || %s::jsonb,
                    error_class = %s, error_message = %s
                WHERE id = %s AND status = 'running'
                """,
                (
                    outcome,
                    clock,
                    clock,
                    json.dumps(cursor_state if cursor_state is not None else job.cursor),
                    json.dumps(metrics or {}),
                    error_class,
                    error_message,
                    job.attempt_id,
                ),
            )
            cursor.execute(
                """
                UPDATE crawl_entity_source_schedule
                SET last_run_at = %s,
                    last_success_at = CASE WHEN %s = 'succeeded' THEN %s ELSE last_success_at END,
                    last_outcome = %s,
                    next_run_at = %s,
                    consecutive_failures = CASE
                        WHEN %s = 'succeeded' THEN 0
                        ELSE consecutive_failures + 1
                    END,
                    updated_at = %s
                WHERE canonical_entity_key = %s AND source = %s AND capability = %s
                """,
                (
                    clock,
                    outcome,
                    clock,
                    outcome,
                    next_run_at,
                    outcome,
                    clock,
                    job.canonical_entity_key,
                    job.source,
                    job.capability,
                ),
            )
            return True

    def inspect(self, *, statuses: Iterable[str] = (), limit: int = 100) -> list[dict[str, Any]]:
        selected = tuple(statuses)
        with self.connection.cursor() as cursor:
            if selected:
                cursor.execute(
                    """
                    SELECT * FROM crawl_jobs
                    WHERE status = ANY(%s)
                    ORDER BY priority DESC, next_run_at, id
                    LIMIT %s
                    """,
                    (list(selected), limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM crawl_jobs ORDER BY priority DESC, next_run_at, id LIMIT %s",
                    (limit,),
                )
            return [dict(row) for row in cursor.fetchall() or []]

    def requeue(self, job_ids: Iterable[int], *, reason: str = "manual_requeue") -> int:
        ids = [int(value) for value in job_ids]
        if not ids:
            return 0
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE crawl_jobs
                SET status = 'queued', next_run_at = now(),
                    lease_owner = NULL, lease_expires_at = NULL,
                    heartbeat_at = NULL, last_outcome = %s, updated_at = now()
                WHERE id = ANY(%s) AND status <> 'running'
                """,
                (reason, ids),
            )
            return cursor.rowcount or 0

    def migrate_json(self, path: Path) -> dict[str, int]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("jobs", [])
        if not isinstance(rows, list):
            raise ValueError("legacy crawl queue must be a list or a jobs list")
        counts = {"read": 0, "inserted": 0, "existing": 0}
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("legacy crawl queue row must be an object")
            counts["read"] += 1
            start = _parse_datetime(raw.get("window_start"))
            end = _parse_datetime(raw.get("window_end"))
            _, inserted = self.enqueue(
                entity_id=int(raw["entity_id"]),
                canonical_entity_key=str(raw.get("canonical_entity_key") or f"db:{int(raw['entity_id'])}"),
                source=str(raw["source"]),
                capability=str(raw.get("capability") or "open_tenders"),
                domain_key=str(raw.get("domain_key") or raw["source"]),
                binding_version=str(raw.get("binding_version") or "legacy-v1"),
                window_start=start,
                window_end=end,
                freshness_deadline=_parse_datetime(raw.get("freshness_deadline") or raw.get("next_run_at")),
                next_run_at=_parse_datetime(raw.get("next_run_at")),
                priority=int(raw.get("priority") or 0),
                cursor=dict(raw.get("cursor") or {}),
                idempotency_key=raw.get("idempotency_key"),
            )
            counts["inserted" if inserted else "existing"] += 1
        return counts


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Durable PostgreSQL crawl queue")
    parser.add_argument("--dsn")
    sub = parser.add_subparsers(dest="command", required=True)
    enqueue_cmd = sub.add_parser("enqueue")
    enqueue_cmd.add_argument("--entity-id", type=int, required=True)
    enqueue_cmd.add_argument("--canonical-entity-key")
    enqueue_cmd.add_argument("--source", required=True)
    enqueue_cmd.add_argument("--capability", default="open_tenders")
    enqueue_cmd.add_argument("--domain", required=True)
    enqueue_cmd.add_argument("--binding-version", required=True)
    enqueue_cmd.add_argument("--window-start", required=True)
    enqueue_cmd.add_argument("--window-end", required=True)
    enqueue_cmd.add_argument("--next-run-at", required=True)
    enqueue_cmd.add_argument("--freshness-deadline", required=True)
    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("--status", action="append", default=[])
    inspect_cmd.add_argument("--limit", type=int, default=100)
    requeue_cmd = sub.add_parser("requeue")
    requeue_cmd.add_argument("job_ids", nargs="+", type=int)
    migrate_cmd = sub.add_parser("migrate-json")
    migrate_cmd.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    with connect(args.dsn) as connection:
        queue = CrawlQueue(connection)
        if args.command == "enqueue":
            job_id, inserted = queue.enqueue(
                entity_id=args.entity_id,
                canonical_entity_key=args.canonical_entity_key,
                source=args.source,
                capability=args.capability,
                domain_key=args.domain,
                binding_version=args.binding_version,
                window_start=_parse_datetime(args.window_start),
                window_end=_parse_datetime(args.window_end),
                freshness_deadline=_parse_datetime(args.freshness_deadline),
                next_run_at=_parse_datetime(args.next_run_at),
            )
            output: Any = {"job_id": job_id, "inserted": inserted}
        elif args.command == "inspect":
            output = queue.inspect(statuses=args.status, limit=args.limit)
        elif args.command == "requeue":
            output = {"requeued": queue.requeue(args.job_ids)}
        else:
            output = queue.migrate_json(args.path)
    print(json.dumps(output, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    sys.exit(main())
