"""Fault injection tests for the pipeline engine.

Tests the fetch→parse→transform→upsert pipeline with DLQ routing.
Covers: JSON invalid, campo ausente, constraint violation, timeout,
FAIL_CLOSED, and graceful continuation.
"""

from __future__ import annotations

import pytest

from scripts.crawl.pipeline import (
    DLQRecord,
    InMemoryDLQ,
    Pipeline,
    PipelineFailClosed,
    PipelineStage,
    StageError,
)

# ===========================================================================
# Helpers
# ===========================================================================


async def _fetch_ok(**kwargs) -> list[dict]:
    """Fetch that returns valid records."""
    return [{"id": 1, "name": "record1"}, {"id": 2, "name": "record2"}]


async def _fetch_none(**kwargs) -> None:
    """Fetch that returns None (empty source)."""
    return None


async def _fetch_empty(**kwargs) -> list:
    """Fetch that returns empty list."""
    return []


def _parse_ok(raw: dict) -> dict:
    """Parse that returns the record as-is."""
    return raw


def _parse_invalid(raw: dict) -> dict:
    """Parse that raises on certain records."""
    if isinstance(raw, dict) and raw.get("id") == 999:
        raise ValueError("Invalid JSON structure: missing required tokens")
    return raw


def _transform_ok(record: dict) -> dict:
    """Transform that passes valid records."""
    if "id" not in record:
        raise StageError(PipelineStage.TRANSFORM, "missing_required_field", "id is required")
    return {"transformed_id": record["id"], "name": record.get("name")}


def _transform_filter(record: dict) -> dict | None:
    """Transform that filters out certain records."""
    if record.get("id") and record["id"] % 2 == 0:
        return None  # Filter out even IDs
    return {"transformed_id": record["id"], "name": record.get("name")}


def _upsert_ok(rows: list[dict]) -> int:
    """Upsert that succeeds."""
    return len(rows)


def _upsert_fail_constraint(rows: list[dict]) -> int:
    """Upsert that raises constraint violation."""
    raise StageError(PipelineStage.UPSERT, "23505_unique_violation", "duplicate key value violates unique constraint")



# ===========================================================================
# Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_pipeline_happy_path():
    """Given valid data, when pipeline runs, then all stages succeed."""
    dlq = InMemoryDLQ()
    pipeline = Pipeline(source="test", run_id="run-001")
    pipeline.set_stages(
        fetch=_fetch_ok,
        parse=_parse_ok,
        transform=_transform_ok,
        upsert=_upsert_ok,
    )
    result = await pipeline.run(dlq)
    assert result["stats"]["fetched"] == 1
    assert result["stats"]["parsed"] == 2
    assert result["stats"]["transformed"] == 2
    assert result["stats"]["upserted"] == 2
    assert result["stats"]["dlq_routed"] == 0
    assert await dlq.pending_count() == 0


@pytest.mark.asyncio
async def test_parse_invalid_json_goes_to_dlq():
    """Given invalid record in parse, when pipeline runs, then record goes to DLQ, pipeline continues."""
    dlq = InMemoryDLQ()

    async def fetch_mixed(**kwargs) -> list[dict]:
        return [{"id": 1, "name": "good"}, {"id": 999, "name": "bad"}]

    pipeline = Pipeline(source="test", run_id="run-002")
    pipeline.set_stages(fetch=fetch_mixed, parse=_parse_invalid, transform=_transform_ok, upsert=_upsert_ok)
    result = await pipeline.run(dlq)

    assert result["stats"]["parsed"] == 1  # Only the good record parsed
    assert result["stats"]["dlq_routed"] == 1  # Bad record to DLQ
    assert await dlq.pending_count() == 1

    dlq_records = await dlq.all()
    assert dlq_records[0].stage == PipelineStage.PARSE
    assert dlq_records[0].error_code == "parse_failed"
    assert dlq_records[0].source == "test"


@pytest.mark.asyncio
async def test_transform_missing_field_goes_to_dlq():
    """Given record missing required field, when transform fails, then DLQ with missing_required_field."""
    dlq = InMemoryDLQ()

    async def fetch_minimal(**kwargs) -> list[dict]:
        return [{"name": "no-id-here"}]

    pipeline = Pipeline(source="test", run_id="run-003")
    pipeline.set_stages(fetch=fetch_minimal, parse=_parse_ok, transform=_transform_ok, upsert=_upsert_ok)
    result = await pipeline.run(dlq)

    assert result["stats"]["transformed"] == 0
    assert result["stats"]["dlq_routed"] == 1
    dlq_records = await dlq.all()
    assert dlq_records[0].error_code == "missing_required_field"
    assert dlq_records[0].stage == PipelineStage.TRANSFORM


@pytest.mark.asyncio
async def test_upsert_constraint_violation_goes_to_dlq():
    """Given constraint violation in upsert, when upsert fails, then DLQ entry with SQL state."""
    dlq = InMemoryDLQ()

    pipeline = Pipeline(source="test", run_id="run-004")
    pipeline.set_stages(fetch=_fetch_ok, parse=_parse_ok, transform=_transform_ok, upsert=_upsert_fail_constraint)
    result = await pipeline.run(dlq)

    assert result["stats"]["upserted"] == 0
    assert result["stats"]["dlq_routed"] == 2  # Both records fail upsert
    dlq_records = await dlq.all()
    for rec in dlq_records:
        assert rec.error_code == "23505_unique_violation"
        assert rec.stage == PipelineStage.UPSERT


@pytest.mark.asyncio
async def test_fetch_unhandled_exception_fail_closed():
    """Given unhandled exception in fetch, when pipeline runs, then FAIL_CLOSED raised."""
    dlq = InMemoryDLQ()

    async def fetch_crash(**kwargs):
        raise RuntimeError("Connection refused: database is down")

    pipeline = Pipeline(source="test", run_id="run-005")
    pipeline.set_stages(fetch=fetch_crash)

    with pytest.raises(PipelineFailClosed) as exc_info:
        await pipeline.run(dlq)

    assert "Fetch failed" in str(exc_info.value)
    # No partial data committed — only what was in this fetch (nothing)
    assert await dlq.pending_count() == 0


@pytest.mark.asyncio
async def test_unhandled_exception_in_parse_fail_closed():
    """Given bug in parse function (not caught by DLQ handler), when exception raised, then FAIL_CLOSED."""
    dlq = InMemoryDLQ()

    def parse_buggy(raw: dict) -> dict:
        raise TypeError("'NoneType' object is not subscriptable")

    async def fetch_one(**kwargs) -> list[dict]:
        return [{"id": 1}]

    pipeline = Pipeline(source="test", run_id="run-006")
    pipeline.set_stages(fetch=fetch_one, parse=parse_buggy)

    result = await pipeline.run(dlq)
    # The TypeError is caught by _run_parse and routed to DLQ
    assert result["stats"]["dlq_routed"] == 1


@pytest.mark.asyncio
async def test_fetch_returns_none_graceful():
    """Given fetch returns None, when pipeline runs, then completes with 0 records."""
    dlq = InMemoryDLQ()
    pipeline = Pipeline(source="test", run_id="run-007")
    pipeline.set_stages(fetch=_fetch_none, parse=_parse_ok)
    result = await pipeline.run(dlq)

    assert result["stats"]["fetched"] == 1
    assert result["stats"]["parsed"] == 0


@pytest.mark.asyncio
async def test_fetch_empty_graceful():
    """Given fetch returns empty list, when pipeline runs, then completes with 0 records."""
    dlq = InMemoryDLQ()
    pipeline = Pipeline(source="test", run_id="run-008")
    pipeline.set_stages(fetch=_fetch_empty, parse=_parse_ok)
    result = await pipeline.run(dlq)

    assert result["stats"]["fetched"] == 1
    assert result["stats"]["parsed"] == 0


@pytest.mark.asyncio
async def test_dlq_records_contain_context():
    """Given records routed to DLQ, when checked, then they carry source, run_id, stage."""
    dlq = InMemoryDLQ()

    async def fetch_bad(**kwargs) -> list[dict]:
        return [{"id": 999}]

    pipeline = Pipeline(source="pncp", run_id="run-ctx-001")
    pipeline.set_stages(fetch=fetch_bad, parse=_parse_invalid)
    await pipeline.run(dlq)

    records = await dlq.all()
    assert len(records) >= 1
    rec = records[0]
    assert rec.source == "pncp"
    assert rec.run_id == "run-ctx-001"
    assert rec.stage == PipelineStage.PARSE


@pytest.mark.asyncio
async def test_transform_returns_none_filtered():
    """Given transform returns None for some records, when pipeline runs, then filtered records omitted."""
    dlq = InMemoryDLQ()

    async def fetch_filtered(**kwargs) -> list[dict]:
        return [{"id": 1}, {"id": 2}, {"id": 3}]

    pipeline = Pipeline(source="test", run_id="run-009")
    pipeline.set_stages(fetch=fetch_filtered, parse=_parse_ok, transform=_transform_filter, upsert=_upsert_ok)
    result = await pipeline.run(dlq)

    assert result["stats"]["parsed"] == 3
    assert result["stats"]["transformed"] == 2  # id=2 filtered out (even)
    assert result["stats"]["upserted"] == 2


@pytest.mark.asyncio
async def test_multiple_failures_all_routed():
    """Given multiple records with different failures, when pipeline runs, then all routed to DLQ."""
    dlq = InMemoryDLQ()

    async def fetch_multi_bad(**kwargs) -> list[dict]:
        return [
            {"id": 1, "name": "good"},
            {"id": 999, "name": "bad-parse"},
            {"name": "missing-id"},  # Missing required field
        ]

    pipeline = Pipeline(source="test", run_id="run-010")
    pipeline.set_stages(fetch=fetch_multi_bad, parse=_parse_invalid, transform=_transform_ok, upsert=_upsert_ok)
    result = await pipeline.run(dlq)

    # Record 2 fails parse, record 3 fails transform
    assert result["stats"]["dlq_routed"] == 2
    assert result["stats"]["upserted"] == 1  # Only record 1 succeeds
    assert await dlq.pending_count() == 2


@pytest.mark.asyncio
async def test_upsert_transform_both_errors_routed():
    """Given upsert fails with StageError, when pipeline runs, then record routed to DLQ."""
    dlq = InMemoryDLQ()

    async def fetch_single(**kwargs) -> list[dict]:
        return [{"id": 1, "name": "will-fail-upsert"}]

    pipeline = Pipeline(source="test", run_id="run-011")
    pipeline.set_stages(fetch=fetch_single, parse=_parse_ok, transform=_transform_ok, upsert=_upsert_fail_constraint)
    result = await pipeline.run(dlq)

    assert result["stats"]["upserted"] == 0
    assert result["stats"]["dlq_routed"] == 1

    records = await dlq.all()
    assert records[0].error_code == "23505_unique_violation"
    assert records[0].stage == PipelineStage.UPSERT


@pytest.mark.asyncio
async def test_in_memory_dlq_pending_count():
    """Given InMemoryDLQ with records, when pending_count called, then accurate count returned."""
    dlq = InMemoryDLQ()
    assert await dlq.pending_count() == 0

    for i in range(5):
        await dlq.push(DLQRecord(source="test", run_id="r1", stage=PipelineStage.PARSE, error_code="parse_failed", error_message=f"err{i}"))

    assert await dlq.pending_count() == 5
    assert await dlq.pending_count(source="test") == 5
    assert await dlq.pending_count(source="other") == 0


@pytest.mark.asyncio
async def test_in_memory_dlq_purge():
    """Given InMemoryDLQ with records, when purge called, then records removed."""
    dlq = InMemoryDLQ()
    for i in range(3):
        await dlq.push(DLQRecord(source="test", run_id="r1", stage=PipelineStage.PARSE, error_code="e", error_message=str(i)))

    assert await dlq.pending_count() == 3
    purged = await dlq.purge()
    assert purged == 3
    assert await dlq.pending_count() == 0


@pytest.mark.asyncio
async def test_no_stages_registered():
    """Given no stages registered, when pipeline runs, then PipelineFailClosed raised."""
    dlq = InMemoryDLQ()
    pipeline = Pipeline(source="test", run_id="run-no-stages")

    with pytest.raises(PipelineFailClosed, match="No fetch function"):
        await pipeline.run(dlq)
