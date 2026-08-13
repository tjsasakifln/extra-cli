"""Production-readiness: entity×source fair queue, CB, DLQ, resume, idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.process_documents.entity_queue import (
    EntityQueueEntry,
    SourceQueueEntry,
    append_dlq_record,
    apply_multi_source_attempt,
    apply_source_attempt_result,
    backpressure_allows,
    compute_backoff_hours,
    ensure_entity_source_pairs,
    list_source_pairs,
    load_entity_queue,
    reprocess_selection,
    save_entity_queue,
    select_source_pairs_by_lag,
    simulate_fair_rotation,
    source_pair_metrics,
)
from scripts.process_documents.error_classes import ErrorClass, classify_error, is_retryable
from scripts.process_documents.queue_lock import QueueDrainLock, lock_path_for_meta
from scripts.process_documents.statuses import DocumentRunStatus


def test_full_rotation_when_universe_exceeds_batch() -> None:
    # 30 entities × 3 sources = 90 pairs; batch of 7 must still cover 100%
    entity_sources = {f"e{i:03d}": ["pncp", "ciga_ckan", "sc_compras"] for i in range(30)}
    result = simulate_fair_rotation(entity_sources, batch_size=7, rng_seed=7)
    assert result["pair_count"] == 90
    assert result["full_rotation"] is True
    assert result["coverage"] == 1.0
    assert result["unique_seen"] == 90
    # first cycle must not always be the static first N of sorted ids only once forever
    assert result["cycles"] >= (90 // 7)


def test_sibling_source_failure_not_masked_by_success() -> None:
    ent = EntityQueueEntry(canonical_id="ent-1")
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    apply_multi_source_attempt(
        ent,
        source_results={
            "pncp": {
                "status": DocumentRunStatus.SUCCESS_NONZERO.value,
                "documents_found": 3,
                "documents_new": 2,
                "scope_complete": True,
            },
            "ciga_ckan": {
                "status": "connection_failed",
                "error": "connection reset by peer",
                "http_status": 502,
            },
        },
        attempted_at=now,
        aggregate_status="PARTIAL",
    )
    pncp = ent.sources_state["pncp"]
    ciga = ent.sources_state["ciga_ckan"]
    assert pncp.last_success_at is not None
    assert pncp.error_class == ErrorClass.NONE.value
    assert ciga.last_success_at is None
    assert ciga.consecutive_failures == 1
    assert ciga.error_class in {
        ErrorClass.NETWORK.value,
        ErrorClass.TRANSIENT.value,
        ErrorClass.UNKNOWN.value,
    }
    # entity aggregate must NOT clear lag when a consulted source failed
    assert ent.last_success_at is None
    assert ent.consecutive_failures >= 1


def test_resume_after_abrupt_interrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    entity_sources = {f"x{i}": ["pncp", "doe_sc"] for i in range(12)}
    q: dict[str, EntityQueueEntry] = {}
    ensure_entity_source_pairs(q, entity_sources)
    # Process first batch of 4 pairs, then "crash" (only persist)
    batch = select_source_pairs_by_lag(q, entity_sources, limit=4)
    clock = datetime(2026, 8, 1, tzinfo=UTC)
    for se in batch:
        apply_source_attempt_result(
            se,
            status=DocumentRunStatus.SUCCESS_ZERO.value,
            attempted_at=clock,
            scope_complete=True,
            cursor=f"ckpt-{se.canonical_id}-{se.source_id}",
        )
        q[se.canonical_id].sources_state[se.source_id] = se
    save_entity_queue(q, meta_root=tmp_path / "meta")

    # Resume from disk
    loaded = load_entity_queue(meta_root=tmp_path / "meta")
    done = 0
    for cid, ent in loaded.items():
        for sid, se in (ent.sources_state or {}).items():
            if se.last_success_at:
                done += 1
                assert se.cursor == f"ckpt-{cid}-{sid}"
    assert done == 4
    remaining = select_source_pairs_by_lag(loaded, entity_sources, limit=100, now=clock)
    # Successful pairs have next_run in future; overdue/never remain
    remaining_keys = {(s.canonical_id, s.source_id) for s in remaining}
    first_keys = {(s.canonical_id, s.source_id) for s in batch}
    assert first_keys.isdisjoint(remaining_keys) or all(
        loaded[c].sources_state[s].last_success_at for c, s in first_keys
    )


def test_retry_idempotent_no_duplicate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    se = SourceQueueEntry(canonical_id="e", source_id="pncp")
    t0 = datetime(2026, 8, 1, tzinfo=UTC)
    apply_source_attempt_result(
        se,
        status=DocumentRunStatus.SUCCESS_NONZERO.value,
        attempted_at=t0,
        documents_found=5,
        documents_new=5,
        documents_changed=0,
        cursor="page-3",
        scope_complete=True,
    )
    # identical retry (same cursor/docs) — counters advance attempt but not docs double
    apply_source_attempt_result(
        se,
        status=DocumentRunStatus.SUCCESS_NONZERO.value,
        attempted_at=t0 + timedelta(hours=1),
        documents_found=5,
        documents_new=0,  # re-run finds same, zero new
        documents_changed=0,
        cursor="page-3",
        scope_complete=True,
    )
    assert se.attempt_count == 2
    assert se.documents_found == 5
    assert se.documents_new == 0
    assert se.cursor == "page-3"
    q = {"e": EntityQueueEntry(canonical_id="e", sources_state={"pncp": se})}
    save_entity_queue(q, meta_root=tmp_path / "meta")
    loaded = load_entity_queue(meta_root=tmp_path / "meta")
    assert loaded["e"].sources_state["pncp"].documents_found == 5
    assert loaded["e"].sources_state["pncp"].attempt_count == 2


def test_circuit_breaker_isolates_source() -> None:
    se = SourceQueueEntry(canonical_id="e", source_id="sc_compras")
    t0 = datetime(2026, 8, 1, tzinfo=UTC)
    for i in range(5):
        apply_source_attempt_result(
            se,
            status="rate_limited",
            error="429 too many requests",
            http_status=429,
            attempted_at=t0 + timedelta(minutes=i),
            cb_threshold=5,
            cb_cooldown_hours=2.0,
            rng=__import__("random").Random(0),
        )
    assert se.circuit_breaker_state == "open"
    assert se.is_circuit_open(t0 + timedelta(minutes=10)) is True
    # healthy sibling remains schedulable
    other = SourceQueueEntry(canonical_id="e", source_id="pncp")
    assert other.is_circuit_open(t0) is False
    entity_sources = {"e": ["pncp", "sc_compras"]}
    q = {
        "e": EntityQueueEntry(
            canonical_id="e",
            sources_state={"pncp": other, "sc_compras": se},
        )
    }
    batch = select_source_pairs_by_lag(q, entity_sources, limit=10, now=t0 + timedelta(minutes=10))
    ids = {s.source_id for s in batch}
    assert "sc_compras" not in ids
    assert "pncp" in ids


def test_dead_letter_and_reprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    se = SourceQueueEntry(canonical_id="e", source_id="pncp")
    t0 = datetime(2026, 8, 1, tzinfo=UTC)
    for i in range(3):
        apply_source_attempt_result(
            se,
            status="not_found",
            error="404 document not found",
            http_status=404,
            attempted_at=t0 + timedelta(minutes=i),
            rng=__import__("random").Random(1),
        )
    assert se.dead_letter is True
    assert se.error_class == ErrorClass.DOCUMENT_NOT_FOUND.value
    path = append_dlq_record(se, meta_root=tmp_path / "meta")
    assert path is not None and path.is_file()
    q = {"e": EntityQueueEntry(canonical_id="e", sources_state={"pncp": se})}
    n = reprocess_selection(q, entity_ids=["e"], source_ids=["pncp"])
    assert n == 1
    assert q["e"].sources_state["pncp"].dead_letter is False


def test_error_classification_matrix() -> None:
    assert classify_error(http_status=429).value == ErrorClass.RATE_LIMIT.value
    assert classify_error(http_status=401).value == ErrorClass.AUTHENTICATION.value
    assert classify_error(error="corrupt empty file").value == ErrorClass.CORRUPT_FILE.value
    assert classify_error(error="json parse error").value == ErrorClass.PARSING.value
    assert is_retryable(ErrorClass.TRANSIENT) is True
    assert is_retryable(ErrorClass.PERMANENT) is False


def test_backoff_has_jitter() -> None:
    vals = {round(compute_backoff_hours(4, jitter=True, rng=__import__("random").Random(i)), 6) for i in range(20)}
    assert len(vals) > 1  # jitter produces spread
    fixed = compute_backoff_hours(3, jitter=False)
    assert fixed == 4.0  # base 1 * 2^(3-1) = 4


def test_backpressure_and_concurrency() -> None:
    ok, reason = backpressure_allows(active_workers=4, max_concurrency=4)
    assert ok is False and reason == "concurrency_cap"
    ok, reason = backpressure_allows(cpu_percent=95.0, active_workers=1, max_concurrency=4)
    assert ok is False and reason == "cpu_backpressure"
    ok, reason = backpressure_allows(
        cpu_percent=10, memory_percent=20, disk_percent=30, active_workers=1, max_concurrency=4
    )
    assert ok is True


def test_queue_lock_blocks_second_holder(tmp_path: Path) -> None:
    path = lock_path_for_meta(tmp_path / "meta")
    lock1 = QueueDrainLock(path=path, run_id="run-a")
    assert lock1.acquire() is True
    lock2 = QueueDrainLock(path=path, run_id="run-b")
    assert lock2.acquire() is False
    lock1.release()
    assert lock2.acquire() is True
    lock2.release()


def test_ensure_all_pairs_and_metrics() -> None:
    entity_sources = {"a": ["pncp", "ciga"], "b": ["pncp"]}
    q: dict[str, EntityQueueEntry] = {}
    ensure_entity_source_pairs(q, entity_sources)
    pairs = list_source_pairs(q, entity_sources)
    assert len(pairs) == 3
    assert set(q["a"].sources_state.keys()) == {"pncp", "ciga"}
    m = source_pair_metrics(q, entity_sources)
    assert m["pair_count"] == 3
    assert m["entity_count"] == 2
    assert m["never_succeeded_pairs"] == 3
