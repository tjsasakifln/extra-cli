"""Real-PostgreSQL regression proof for provenance terminal persistence (#342)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator

import psycopg2
import psycopg2.extras
import pytest

from scripts.crawl import provenance_sync
from scripts.crawl.provenance import (
    ProvenanceRunNotFoundError,
    ProvenanceRunStateError,
    ProvenanceSourceMismatchError,
    ProvenanceTracker,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def real_tracker(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[ProvenanceTracker, str, list[str]]]:
    if os.getenv("REQUIRE_REAL_DB", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("REQUIRE_REAL_DB=1 is required for the PostgreSQL provenance proof")

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("TEST_DSN")
    if not dsn:
        pytest.fail("REQUIRE_REAL_DB=1 but LOCAL_DATALAKE_DSN/TEST_DSN is unset")

    try:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pipeline_runs LIMIT 1")
    except Exception as exc:
        pytest.fail(f"real PostgreSQL pipeline_runs is unavailable: {exc}")

    tracker = ProvenanceTracker(conn_string=dsn)
    monkeypatch.setattr(provenance_sync, "_tracker", tracker)
    run_ids: list[str] = []
    yield tracker, dsn, run_ids

    if run_ids:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pipeline_runs WHERE run_id = ANY(%s)", (run_ids,))


def _new_run_id(run_ids: list[str], label: str) -> str:
    run_id = f"issue-342-{label}-{uuid.uuid4().hex}"
    run_ids.append(run_id)
    return run_id


def _start(tracker: ProvenanceTracker, run_id: str, source: str) -> None:
    asyncio.run(tracker.start_run(run_id, source, mode="incremental"))


def _get_run(dsn: str, run_id: str) -> dict:
    with psycopg2.connect(dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM pipeline_runs WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
    assert row is not None
    return dict(row)


def test_complete_persists_every_count_in_its_schema_column(real_tracker) -> None:
    tracker, dsn, run_ids = real_tracker
    run_id = _new_run_id(run_ids, "complete")
    _start(tracker, run_id, "pcp")

    provenance_sync.provenance_complete(
        run_id=run_id,
        source="pcp",
        records_fetched=101,
        records_deduplicated=11,
        records_upserted=89,
        records_dlq=3,
        records_failed=2,
        pages_planned=9,
        pages_completed=8,
        watermarks_committed=7,
        duration_ms=6543,
    )

    row = _get_run(dsn, run_id)
    assert row["source"] == "pcp"
    assert row["status"] == "completed"
    assert row["completed_at"] is not None
    assert row["records_fetched"] == 101
    assert row["records_deduplicated"] == 11
    assert row["records_upserted"] == 89
    assert row["records_dlq"] == 3
    assert row["records_failed"] == 2
    assert row["pages_planned"] == 9
    assert row["pages_completed"] == 8
    assert row["watermarks_committed"] == 7
    assert row["duration_ms"] == 6543


def test_fail_persists_error_counts_and_duration(real_tracker) -> None:
    tracker, dsn, run_ids = real_tracker
    run_id = _new_run_id(run_ids, "fail")
    _start(tracker, run_id, "dom_sc")

    provenance_sync.provenance_fail(
        run_id=run_id,
        source="dom_sc",
        error_message="upstream timed out",
        records_fetched=13,
        records_deduplicated=2,
        records_upserted=8,
        records_dlq=1,
        records_failed=1,
        pages_planned=5,
        pages_completed=4,
        watermarks_committed=3,
        duration_ms=4321,
    )

    row = _get_run(dsn, run_id)
    assert row["source"] == "dom_sc"
    assert row["status"] == "failed"
    assert row["completed_at"] is not None
    assert row["error_message"] == "upstream timed out"
    assert row["records_fetched"] == 13
    assert row["records_deduplicated"] == 2
    assert row["records_upserted"] == 8
    assert row["records_dlq"] == 1
    assert row["records_failed"] == 1
    assert row["pages_planned"] == 5
    assert row["pages_completed"] == 4
    assert row["watermarks_committed"] == 3
    assert row["duration_ms"] == 4321


def test_wrong_source_and_missing_run_fail_closed(real_tracker) -> None:
    tracker, dsn, run_ids = real_tracker
    run_id = _new_run_id(run_ids, "identity")
    _start(tracker, run_id, "pcp")

    with pytest.raises(ProvenanceSourceMismatchError, match="expected=doe_sc actual=pcp"):
        provenance_sync.provenance_complete(run_id=run_id, source="doe_sc")

    row = _get_run(dsn, run_id)
    assert row["status"] == "running"
    assert row["records_fetched"] == 0

    with pytest.raises(ProvenanceRunNotFoundError, match="not found"):
        provenance_sync.provenance_fail(
            run_id=f"missing-{uuid.uuid4().hex}",
            source="pcp",
            error_message="cannot persist",
        )


def test_terminal_transition_is_single_use_and_does_not_overwrite_counts(real_tracker) -> None:
    tracker, dsn, run_ids = real_tracker
    run_id = _new_run_id(run_ids, "terminal")
    _start(tracker, run_id, "tce_sc")
    provenance_sync.provenance_complete(
        run_id=run_id,
        source="tce_sc",
        records_fetched=17,
        duration_ms=25,
    )

    with pytest.raises(ProvenanceRunStateError, match="status=completed"):
        provenance_sync.provenance_fail(
            run_id=run_id,
            source="tce_sc",
            error_message="late failure",
            records_fetched=999,
        )

    row = _get_run(dsn, run_id)
    assert row["status"] == "completed"
    assert row["records_fetched"] == 17
    assert row["duration_ms"] == 25
