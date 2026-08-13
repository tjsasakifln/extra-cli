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
from scripts.ops.truth_plane_sli import observe, set_kill_switch


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


def test_truth_plane_sli_without_enabled_definitions_is_blocked_without_db_mutation() -> None:
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = []
    cursor.fetchone.side_effect = [
        {"singleton": True, "enabled": False},
        {"id": 17},
        None,
        None,
    ]
    fixed_now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    result = observe(connection, actor="test-sli-no-definitions", now=fixed_now)

    assert result["status"] == "BLOCKED"
    assert result["metric_count"] == 0
    assert result["denominator_sum"] == 0
    insert_call = next(
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO truth_plane_sli_reviews" in call.args[0]
    )
    assert insert_call.args[1][0] == insert_call.args[1][1] == fixed_now
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


def _dlq_test_entity_state(dsn: str) -> tuple[int, bool, bool]:
    with connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sc_public_entities (razao_social, cnpj_8, is_active)
            VALUES ('Test runtime truth entity', '98765432', TRUE)
            ON CONFLICT (cnpj_8) DO NOTHING
            RETURNING id, is_active
            """
        )
        created = cursor.fetchone()
        if created:
            return int(created["id"]), True, bool(created["is_active"])
        cursor.execute(
            "SELECT id, is_active FROM sc_public_entities WHERE cnpj_8 = '98765432' FOR UPDATE"
        )
        existing = cursor.fetchone()
        cursor.execute("UPDATE sc_public_entities SET is_active = TRUE WHERE id = %s", (existing["id"],))
        return int(existing["id"]), False, bool(existing["is_active"])


def _clean_test_jobs(dsn: str) -> None:
    with connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE crawl_jobs SET dlq_entry_id = NULL WHERE source LIKE 'test_queue_%'")
        cursor.execute("DELETE FROM dlq_entries WHERE source LIKE 'test_queue_%'")
        cursor.execute("DELETE FROM crawl_jobs WHERE source LIKE 'test_queue_%'")
        cursor.execute("DELETE FROM crawl_entity_source_schedule WHERE source LIKE 'test_queue_%'")


@pytest.mark.database
@pytest.mark.integration
def test_transactional_dlq_poison_blocked_selective_replay_and_resolve(runtime_queue_dsn: str) -> None:
    dsn = runtime_queue_dsn
    _clean_test_jobs(dsn)
    entity_id, entity_created, entity_was_active = _dlq_test_entity_state(dsn)
    now = datetime.now(UTC).replace(microsecond=0)
    common = {
        "entity_id": entity_id,
        "capability": "open_tenders",
        "binding_version": "test-dlq-v1",
        "window_start": now,
        "window_end": now + timedelta(minutes=5),
        "freshness_deadline": now + timedelta(minutes=10),
        "next_run_at": now,
        "priority": 3_000_000,
    }
    try:
        with connect(dsn) as connection:
            queue = CrawlQueue(connection)
            poison_id, _ = queue.enqueue(
                source="test_queue_poison",
                domain_key="poison.example",
                max_attempts=1,
                **common,
            )
            blocked_id, _ = queue.enqueue(
                source="test_queue_blocked",
                domain_key="blocked.example",
                max_attempts=5,
                **common,
            )

        with connect(dsn) as connection:
            jobs = CrawlQueue(connection).claim(worker_id="poison-worker", limit=2, now=now)
            by_id = {job.id: job for job in jobs}
            queue = CrawlQueue(connection)
            assert queue.finish(
                by_id[poison_id],
                worker_id="poison-worker",
                outcome="failed",
                next_run_at=now + timedelta(hours=1),
                error_class="POISON_PAYLOAD",
                error_message="deterministic poison",
                payload_pointer={"raw_uri": "raw://sha256/poison"},
                dlq_owner="data-ops",
            )
            assert queue.finish(
                by_id[blocked_id],
                worker_id="poison-worker",
                outcome="blocked",
                next_run_at=now + timedelta(hours=1),
                error_class="AUTH_BLOCKED",
                error_message="credential unavailable",
            )
            # The terminal transition is ownership-guarded and cannot duplicate.
            assert not queue.finish(
                by_id[poison_id],
                worker_id="poison-worker",
                outcome="failed",
                next_run_at=now + timedelta(hours=1),
                error_class="POISON_PAYLOAD",
            )

        with connect(dsn) as connection:
            queue = CrawlQueue(connection)
            assert queue.inspect_dlq(error_class="NOT_THE_POISON") == []
            poison = queue.inspect_dlq(
                source="test_queue_poison",
                canonical_entity_key=f"db:{entity_id}",
                error_class="POISON_PAYLOAD",
            )
            blocked = queue.inspect_dlq(source="test_queue_blocked", error_class="AUTH_BLOCKED")
            assert len(poison) == len(blocked) == 1
            assert poison[0]["payload_pointer"] == {"raw_uri": "raw://sha256/poison"}
            assert poison[0]["owner"] == "data-ops"
            assert queue.replay_dlq(actor="operator", error_class="SOME_OTHER_CLASS") == []
            assert queue.replay_dlq(
                actor="operator",
                source="test_queue_poison",
                error_class="POISON_PAYLOAD",
            ) == [poison[0]["id"]]

        with connect(dsn) as connection:
            replayed = CrawlQueue(connection).claim(worker_id="replay-worker", limit=1)
            assert [job.id for job in replayed] == [poison_id]
            assert replayed[0].attempt_count == 1
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) AS count FROM crawl_job_attempts WHERE job_id = %s", (poison_id,))
                assert int(cursor.fetchone()["count"]) == 2
                cursor.execute("SELECT status, replay_count FROM dlq_entries WHERE id = %s", (poison[0]["id"],))
                assert tuple(cursor.fetchone().values()) == ("replayed", 1)
            assert CrawlQueue(connection).finish(
                replayed[0],
                worker_id="replay-worker",
                outcome="succeeded",
                next_run_at=now + timedelta(days=1),
            )

        with connect(dsn) as connection:
            queue = CrawlQueue(connection)
            assert queue.resolve_dlq(
                [poison[0]["id"], blocked[0]["id"]],
                actor="operator",
                resolution="poison corrected; auth routed to owner",
            ) == 2
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) AS count FROM dlq_entries WHERE id = ANY(%s) AND status = 'archived'",
                    ([poison[0]["id"], blocked[0]["id"]],),
                )
                assert int(cursor.fetchone()["count"]) == 2
                cursor.execute("SELECT status FROM crawl_jobs WHERE id = %s", (blocked_id,))
                assert cursor.fetchone()["status"] == "blocked"
    finally:
        _clean_test_jobs(dsn)
        with connect(dsn) as connection, connection.cursor() as cursor:
            if entity_created:
                cursor.execute("DELETE FROM sc_public_entities WHERE id = %s", (entity_id,))
            else:
                cursor.execute(
                    "UPDATE sc_public_entities SET is_active = %s WHERE id = %s",
                    (entity_was_active, entity_id),
                )


@pytest.mark.database
@pytest.mark.integration
def test_truth_plane_sli_missing_denominators_preserve_last_valid_and_route_alerts(
    runtime_queue_dsn: str,
) -> None:
    dsn = runtime_queue_dsn
    route_name = "000-test-ops"
    marker_metric = f"test_sli_marker_{os.getpid()}"
    observation_now = datetime(2099, 8, 13, 12, 0, tzinfo=UTC)
    with connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM truth_plane_alert_events WHERE route_name = %s", (route_name,))
        cursor.execute("DELETE FROM truth_plane_alert_routes WHERE route_name = %s", (route_name,))
        cursor.execute("DELETE FROM truth_plane_sli_reviews WHERE actor LIKE 'test-sli-%'")
        cursor.execute("DELETE FROM truth_plane_cost_observations WHERE source = 'test-sli-source'")
        cursor.execute("DELETE FROM truth_plane_slo_definitions WHERE metric_name = %s", (marker_metric,))
        cursor.execute(
            """
            INSERT INTO truth_plane_slo_definitions (
                metric_name, stage, window_seconds, denominator_contract,
                objective_operator, objective_value, unit, alert_before_ratio
            ) VALUES (%s, 'test_isolation', 60, 'test-only marker', 'lte', 0, 'records', 1)
            """,
            (marker_metric,),
        )
        cursor.execute(
            """
            INSERT INTO truth_plane_alert_routes (route_name, destination)
            VALUES (%s, 'test://ops')
            """,
            (route_name,),
        )
        cursor.execute(
            """
            INSERT INTO truth_plane_sli_reviews (
                window_start, window_end, status, metrics, metric_count,
                unknown_count, breach_count, denominator_sum, definition_hash, actor
            ) VALUES (NOW() - interval '1 hour', NOW(), 'VALID', '[{"state":"OK"}]', 1, 0, 0, 1, 'prior-valid', 'test-sli-prior')
            RETURNING id
            """
        )
        prior_valid_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO truth_plane_cost_observations
                (source, unit_type, unit_count, cost_brl, provenance, observed_at)
            VALUES ('test-sli-source', 'document', 10, 5, '{"invoice":"fixture"}', %s)
            """,
            (observation_now - timedelta(days=1),),
        )

    try:
        with connect(dsn) as connection:
            set_kill_switch(connection, enabled=False, reason="test baseline", actor="test-sli-operator")
            first = observe(connection, actor="test-sli-observe-1", now=observation_now)
        assert first["status"] == "BLOCKED"
        assert first["unknown_count"] > 0
        assert first["denominator_sum"] > 0
        assert first["last_valid_review"]["id"] == prior_valid_id
        assert all(metric["window_seconds"] > 0 for metric in first["metrics"])
        assert all("denominator" in metric and "denominator_contract" in metric for metric in first["metrics"])
        public_metrics = [m for m in first["metrics"] if m["stage"] == "canonical_to_public_read_v1"]
        assert public_metrics and all(metric["state"] == "UNKNOWN" for metric in public_metrics)
        cost = next(m for m in first["metrics"] if m["metric_name"] == "operational_cost_per_public_unit")
        assert cost["value"] == 0.5

        with connect(dsn) as connection:
            second = observe(connection, actor="test-sli-observe-2", now=observation_now)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT min(occurrence_count) AS minimum,
                           bool_and(delivery_status = 'PENDING') AS routed
                    FROM truth_plane_alert_events
                    WHERE route_name = %s
                    """,
                    (route_name,),
                )
                alert_state = cursor.fetchone()
        assert second["status"] == "BLOCKED"
        assert int(alert_state["minimum"]) >= 2
        assert alert_state["routed"] is True

        with connect(dsn) as connection:
            enabled = set_kill_switch(
                connection,
                enabled=True,
                reason="consumer isolation threshold exceeded",
                actor="test-sli-operator",
            )
            assert enabled["enabled"] is True
            blocked = observe(connection, actor="test-sli-killed", now=observation_now)
            assert blocked["status"] == "BLOCKED"
            assert blocked["kill_switch"]["enabled"] is True
            set_kill_switch(connection, enabled=False, reason="test cleanup", actor="test-sli-operator")
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) AS count FROM truth_plane_kill_switch_history WHERE changed_by = 'test-sli-operator'"
                )
                assert int(cursor.fetchone()["count"]) >= 3
    finally:
        with connect(dsn) as connection:
            set_kill_switch(
                connection,
                enabled=False,
                reason="test finally cleanup",
                actor="test-sli-operator",
            )
        with connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM truth_plane_alert_events WHERE route_name = %s", (route_name,))
            cursor.execute("DELETE FROM truth_plane_alert_routes WHERE route_name = %s", (route_name,))
            cursor.execute("DELETE FROM truth_plane_sli_reviews WHERE actor LIKE 'test-sli-%'")
            cursor.execute("DELETE FROM truth_plane_cost_observations WHERE source = 'test-sli-source'")
            cursor.execute("DELETE FROM truth_plane_slo_definitions WHERE metric_name = %s", (marker_metric,))
            cursor.execute(
                "DELETE FROM truth_plane_kill_switch_history WHERE changed_by = 'test-sli-operator'"
            )


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
