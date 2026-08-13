"""Durable queue, continuous scheduler and worker admission contracts."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl.runtime_queue import CrawlQueue, connect
from scripts.crawl.scheduler import (
    SchedulePair,
    SchedulePolicyRegistry,
    load_pairs_from_database,
    reconcile_schedule,
)
from scripts.crawl.worker import AdmissionLimits, CrawlWorker, admission_blockers


def _pairs(entity_count: int = 1093) -> list[SchedulePair]:
    sources = ("pncp", "ciga_dom", "sc_compras", "transparencia")
    return [
        SchedulePair(
            entity_id=entity_id,
            source=source,
            reason="synthetic_applicability_contract",
            binding_version="test-binding-v1",
        )
        for entity_id in range(1, entity_count + 1)
        for source in sources
    ]


def test_scheduler_dry_run_is_deterministic_for_1093_entities_and_4372_pairs() -> None:
    pairs = _pairs()
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    first = reconcile_schedule(object(), pairs, expected_entities=1093, now=now, dry_run=True)
    second = reconcile_schedule(object(), reversed(pairs), expected_entities=1093, now=now, dry_run=True)

    assert first == second
    assert first["entity_count"] == 1093
    assert first["pair_count"] == 4372
    assert first["queued"] == 4372
    assert first["fully_reconciled"] is True


def test_scheduler_rejects_universe_or_route_gap() -> None:
    with pytest.raises(ValueError, match="active universe mismatch"):
        reconcile_schedule(object(), _pairs(3), expected_entities=1093, dry_run=True)

    pairs = [SchedulePair(entity_id=1, source="pncp", capability="documents")]
    with pytest.raises(ValueError, match="without open-tender route"):
        reconcile_schedule(object(), pairs, expected_entities=1, dry_run=True)


@pytest.mark.parametrize(
    ("load", "memory", "disk", "expected"),
    [
        (8.0, 0.5, 0.5, ["cpu_pressure"]),
        (0.1, 0.05, 0.5, ["memory_pressure"]),
        (0.1, 0.5, 0.05, ["disk_pressure"]),
        (0.1, 0.5, 0.5, []),
    ],
)
def test_worker_backpressure_is_fail_closed(
    load: float,
    memory: float,
    disk: float,
    expected: list[str],
) -> None:
    blockers = admission_blockers(
        AdmissionLimits(max_load_per_cpu=0.9),
        load_average=load,
        cpu_count=4,
        memory_ratio=memory,
        disk_ratio=disk,
    )
    assert blockers == expected


def test_queue_migration_rejects_invalid_legacy_shape(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text(json.dumps({"jobs": {"not": "a list"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        CrawlQueue(object()).migrate_json(path)


def test_runtime_queue_connection_always_closes() -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    with patch("psycopg2.connect", return_value=connection):
        with connect("postgresql://example") as yielded:
            assert yielded is connection
    connection.close.assert_called_once()


def test_claim_commits_admission_transaction_before_return() -> None:
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = {"expired_count": 0}
    cursor.fetchall.return_value = []

    assert CrawlQueue(connection).claim(worker_id="test-worker") == []

    connection.commit.assert_called_once()


def test_worker_loads_policy_before_claiming_job() -> None:
    worker = CrawlWorker(dsn="postgresql://example")
    with (
        patch("scripts.crawl.worker.admission_blockers", return_value=[]),
        patch(
            "scripts.crawl.worker.SchedulePolicyRegistry.load",
            side_effect=ValueError("invalid policy"),
        ),
        patch("scripts.crawl.worker.connect") as queue_connect,
        pytest.raises(ValueError, match="invalid policy"),
    ):
        worker.run_once()
    queue_connect.assert_not_called()


def test_canonical_queue_migration_is_constraint_name_independent() -> None:
    sql = Path("db/migrations/083_crawl_queue_canonical_entity.sql").read_text(encoding="utf-8")
    assert "constraint_row.contype = 'p'" in sql
    assert "constraint_row.conrelid = 'crawl_entity_source_schedule'::regclass" in sql
    assert "pkey_columns IS DISTINCT FROM" in sql
    assert "OR (status <> 'running' AND finished_at IS NOT NULL)" in Path(
        "db/migrations/079_crawl_runtime_queue.sql"
    ).read_text(encoding="utf-8")


@pytest.fixture
def runtime_queue_dsn() -> str:
    if not (
        os.getenv("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}
        or os.getenv("RESILIENCE_REQUIRE_DB", "").lower() in {"1", "true", "yes"}
    ):
        pytest.skip("REQUIRE_REAL_DB=1 or RESILIENCE_REQUIRE_DB=1 required")
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("LOCAL_DATALAKE_DSN or DATABASE_URL not set")
    return dsn


@pytest.mark.database
@pytest.mark.integration
def test_real_active_universe_dry_run_reconciles_1093_and_4372(runtime_queue_dsn: str) -> None:
    from scripts.ops.materialize_canonical_spine import ensure_target_universe

    with connect(runtime_queue_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM v_target_universe_active")
        active_count = int(cursor.fetchone()["count"])
        if active_count == 0:
            materialized = ensure_target_universe(connection, dsn=runtime_queue_dsn)
            assert materialized["status"] == "ok", materialized

    with connect(runtime_queue_dsn) as connection:
        pairs = load_pairs_from_database(connection)
        result = reconcile_schedule(
            connection,
            pairs,
            expected_entities=1093,
            now=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            dry_run=True,
        )
    assert result["entity_count"] == 1093
    assert result["pair_count"] == 4372
    assert result["fully_reconciled"] is True


def _active_entity_id(dsn: str) -> int:
    with connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM sc_public_entities WHERE is_active ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        if not row:
            pytest.fail("real database has no active sc_public_entities row")
        return int(row["id"])


def _clean_test_jobs(dsn: str) -> None:
    with connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM crawl_jobs WHERE source LIKE 'test_queue_%'")
        cursor.execute("DELETE FROM crawl_entity_source_schedule WHERE source LIKE 'test_queue_%'")


@pytest.mark.database
@pytest.mark.integration
def test_queue_idempotency_concurrent_leases_restart_and_json_migration(
    runtime_queue_dsn: str,
    tmp_path: Path,
) -> None:
    dsn = runtime_queue_dsn
    _clean_test_jobs(dsn)
    entity_id = _active_entity_id(dsn)
    now = datetime.now(UTC).replace(microsecond=0)
    common = {
        "entity_id": entity_id,
        "capability": "open_tenders",
        "binding_version": "test-v1",
        "window_start": now,
        "window_end": now + timedelta(hours=1),
        "freshness_deadline": now + timedelta(hours=1),
        "next_run_at": now,
        "priority": 2_000_000,
        "domain_concurrency_limit": 4,
    }
    try:
        with connect(dsn) as connection:
            queue = CrawlQueue(connection)
            first_id, inserted = queue.enqueue(
                source="test_queue_a",
                domain_key="test-a.example",
                **common,
            )
            repeated_id, repeated = queue.enqueue(
                source="test_queue_a",
                domain_key="test-a.example",
                **common,
            )
            second_id, second_inserted = queue.enqueue(
                source="test_queue_b",
                domain_key="test-b.example",
                **common,
            )
        assert inserted is True
        assert repeated is False
        assert second_inserted is True
        assert first_id == repeated_id

        barrier = threading.Barrier(2)
        claims: list[tuple[str, list[int]]] = []

        def claim(worker_id: str) -> None:
            with connect(dsn) as connection:
                barrier.wait()
                jobs = CrawlQueue(connection).claim(
                    worker_id=worker_id,
                    limit=1,
                    lease_seconds=60,
                    now=now + timedelta(seconds=1),
                )
                claims.append((worker_id, [job.id for job in jobs]))

        threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        claimed_ids = [job_id for _, ids in claims for job_id in ids]
        assert len(claimed_ids) == 2
        assert set(claimed_ids) == {first_id, second_id}

        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE crawl_jobs SET lease_expires_at = %s WHERE id = %s",
                (now - timedelta(seconds=1), claimed_ids[0]),
            )
        with connect(dsn) as connection:
            reclaimed = CrawlQueue(connection).reclaim_expired(now=now)
        assert reclaimed == 1

        legacy = tmp_path / "legacy.json"
        legacy.write_text(
            json.dumps(
                [
                    {
                        "entity_id": entity_id,
                        "source": "test_queue_legacy",
                        "capability": "open_tenders",
                        "domain_key": "legacy.example",
                        "binding_version": "legacy-v1",
                        "window_start": now.isoformat(),
                        "window_end": (now + timedelta(hours=1)).isoformat(),
                        "freshness_deadline": (now + timedelta(hours=1)).isoformat(),
                        "next_run_at": now.isoformat(),
                    }
                ]
            ),
            encoding="utf-8",
        )
        with connect(dsn) as connection:
            migrated = CrawlQueue(connection).migrate_json(legacy)
        assert migrated == {"read": 1, "inserted": 1, "existing": 0}
    finally:
        _clean_test_jobs(dsn)


@pytest.mark.database
@pytest.mark.integration
def test_reclaim_expired_counts_jobs_even_without_attempt_row(runtime_queue_dsn: str) -> None:
    dsn = runtime_queue_dsn
    _clean_test_jobs(dsn)
    entity_id = _active_entity_id(dsn)
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        with connect(dsn) as connection:
            job_id, inserted = CrawlQueue(connection).enqueue(
                entity_id=entity_id,
                source="test_queue_orphan_attempt",
                capability="open_tenders",
                domain_key="orphan-attempt.example",
                binding_version="test-v1",
                window_start=now,
                window_end=now + timedelta(hours=1),
                freshness_deadline=now + timedelta(hours=1),
                next_run_at=now,
            )
            assert inserted is True
        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE crawl_jobs
                SET status = 'running', lease_owner = 'missing-attempt-worker',
                    lease_expires_at = %s, attempt_count = 1
                WHERE id = %s
                """,
                (now - timedelta(seconds=1), job_id),
            )
        with connect(dsn) as connection:
            assert CrawlQueue(connection).reclaim_expired(now=now) == 1
        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM crawl_jobs WHERE id = %s", (job_id,))
            assert cursor.fetchone()["status"] == "queued"
    finally:
        _clean_test_jobs(dsn)


@pytest.mark.database
@pytest.mark.integration
def test_domain_concurrency_limit_serializes_workers(runtime_queue_dsn: str) -> None:
    dsn = runtime_queue_dsn
    _clean_test_jobs(dsn)
    entity_id = _active_entity_id(dsn)
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        with connect(dsn) as connection:
            queue = CrawlQueue(connection)
            for suffix in ("c", "d"):
                queue.enqueue(
                    entity_id=entity_id,
                    source=f"test_queue_{suffix}",
                    capability="open_tenders",
                    domain_key="strict-limit.example",
                    binding_version="test-v1",
                    window_start=now,
                    window_end=now + timedelta(hours=1),
                    freshness_deadline=now + timedelta(hours=1),
                    next_run_at=now,
                    priority=2_000_000,
                    domain_concurrency_limit=1,
                )
        barrier = threading.Barrier(2)
        claimed: list[int] = []

        def claim_one(worker_id: str) -> None:
            with connect(dsn) as connection:
                barrier.wait()
                jobs = CrawlQueue(connection).claim(
                    worker_id=worker_id,
                    limit=1,
                    lease_seconds=60,
                    now=now + timedelta(seconds=1),
                )
                claimed.extend(job.id for job in jobs)

        threads = [threading.Thread(target=claim_one, args=(f"domain-worker-{index}",)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert len(claimed) == 1
    finally:
        _clean_test_jobs(dsn)


@pytest.mark.database
@pytest.mark.integration
def test_failed_attempt_retries_with_cursor_and_metrics(runtime_queue_dsn: str) -> None:
    dsn = runtime_queue_dsn
    _clean_test_jobs(dsn)
    entity_id = _active_entity_id(dsn)
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        with connect(dsn) as connection:
            queue = CrawlQueue(connection)
            queue.enqueue(
                entity_id=entity_id,
                source="test_queue_retry",
                capability="open_tenders",
                domain_key="retry.example",
                binding_version="test-v1",
                window_start=now,
                window_end=now + timedelta(hours=1),
                freshness_deadline=now + timedelta(hours=1),
                next_run_at=now,
                max_attempts=3,
            )
        with connect(dsn) as connection:
            job = CrawlQueue(connection).claim(
                worker_id="retry-worker",
                lease_seconds=60,
                now=now + timedelta(seconds=1),
            )[0]
        with connect(dsn) as connection:
            assert CrawlQueue(connection).finish(
                job,
                worker_id="retry-worker",
                outcome="failed",
                next_run_at=now + timedelta(minutes=5),
                cursor_state={"page": 7},
                metrics={"latency_ms": 123, "pages": 6},
                error_class="UPSTREAM_TRANSIENT",
                error_message="HTTP 504",
            )
        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status, cursor, attempt_count FROM crawl_jobs WHERE id = %s", (job.id,))
            queued = cursor.fetchone()
            cursor.execute(
                "SELECT status, run_id, cursor, metrics FROM crawl_job_attempts WHERE id = %s",
                (job.attempt_id,),
            )
            attempt = cursor.fetchone()
        assert queued == {"status": "queued", "cursor": {"page": 7}, "attempt_count": 1}
        assert attempt["status"] == "failed"
        assert attempt["run_id"] == job.run_id
        assert attempt["cursor"] == {"page": 7}
        assert attempt["metrics"] == {"latency_ms": 123, "pages": 6}
    finally:
        _clean_test_jobs(dsn)


@pytest.mark.database
@pytest.mark.integration
def test_successful_job_stays_terminal_until_schedule_is_due(runtime_queue_dsn: str) -> None:
    dsn = runtime_queue_dsn
    _clean_test_jobs(dsn)
    entity_id = _active_entity_id(dsn)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    next_run = now + timedelta(hours=1)
    source = "test_queue_recurring"
    pair = SchedulePair(
        entity_id=entity_id,
        source=source,
        reason="recurrence_regression",
        binding_version="test-v1",
    )
    registry = SchedulePolicyRegistry(
        {
            "schema_version": "crawl-schedule-policy/v1",
            "policy_version": "test-v1",
            "default": {
                "sla_hours": 1,
                "recheck_not_applicable_hours": 1,
                "recheck_blocked_hours": 1,
                "recheck_failed_hours": 1,
                "jitter_seconds": 0,
                "max_attempts": 3,
                "domain_concurrency_limit": 1,
            },
            "sources": {source: {"domain": "recurring.example"}},
        }
    )
    try:
        with connect(dsn) as connection:
            first = reconcile_schedule(
                connection,
                [pair],
                expected_entities=1,
                now=now,
                policy_registry=registry,
            )
            assert first["queued"] == 1
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE crawl_jobs SET priority = 2000000 WHERE source = %s",
                    (source,),
                )
        with connect(dsn) as connection:
            job = CrawlQueue(connection).claim(
                worker_id="recurring-worker",
                lease_seconds=60,
                now=now + timedelta(seconds=1),
            )[0]
            assert job.source == source
        with connect(dsn) as connection:
            assert CrawlQueue(connection).finish(
                job,
                worker_id="recurring-worker",
                outcome="succeeded",
                next_run_at=next_run,
            )
        with connect(dsn) as connection:
            early = reconcile_schedule(
                connection,
                [pair],
                expected_entities=1,
                now=next_run - timedelta(minutes=1),
                policy_registry=registry,
            )
            assert early["deferred"] == 1
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status, attempt_count FROM crawl_jobs WHERE id = %s",
                    (job.id,),
                )
                assert cursor.fetchone() == {"status": "succeeded", "attempt_count": 0}
                cursor.execute("SELECT COUNT(*) AS count FROM crawl_jobs WHERE source = %s", (source,))
                assert cursor.fetchone()["count"] == 1
        with connect(dsn) as connection:
            due = reconcile_schedule(
                connection,
                [pair],
                expected_entities=1,
                now=next_run,
                policy_registry=registry,
            )
            assert due["queued"] == 1
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status, COUNT(*) AS count FROM crawl_jobs WHERE source = %s GROUP BY status",
                    (source,),
                )
                assert {row["status"]: row["count"] for row in cursor.fetchall()} == {
                    "queued": 1,
                    "succeeded": 1,
                }
    finally:
        _clean_test_jobs(dsn)


@pytest.mark.database
@pytest.mark.integration
def test_rollback_083_refuses_legacy_identity_collisions(runtime_queue_dsn: str) -> None:
    import psycopg2

    dsn = runtime_queue_dsn
    source = "test_queue_rollback_guard"
    _clean_test_jobs(dsn)
    entity_id = _active_entity_id(dsn)
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        with connect(dsn) as connection, connection.cursor() as cursor:
            for canonical_key in ("test:rollback:a", "test:rollback:b"):
                cursor.execute(
                    """
                    INSERT INTO crawl_entity_source_schedule (
                        canonical_entity_key, entity_id, source, capability,
                        applicability, applicability_reason, policy_version,
                        binding_version, domain_key, next_run_at, freshness_deadline
                    ) VALUES (%s, %s, %s, 'open_tenders', 'APPLICABLE',
                              'rollback_guard_test', 'test-v1', 'test-v1',
                              'rollback.example', %s, %s)
                    """,
                    (canonical_key, entity_id, source, now, now + timedelta(hours=1)),
                )

        rollback_sql = Path("db/rollback/083_crawl_queue_canonical_entity_rollback.sql").read_text(
            encoding="utf-8"
        )
        with pytest.raises(psycopg2.DatabaseError, match="canonical rows collide"):
            with connect(dsn) as connection, connection.cursor() as cursor:
                cursor.execute(rollback_sql)

        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN ('crawl_jobs', 'crawl_entity_source_schedule')
                  AND column_name = 'canonical_entity_key'
                """
            )
            assert cursor.fetchone()["count"] == 2
    finally:
        _clean_test_jobs(dsn)
