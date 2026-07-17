"""Tests for DLQ backoff, DurableDLQ (mocked), and DLQWorker.

Integration tests requiring database are in ``test_dlq_integration.py``
(marked with ``@pytest.mark.database``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.crawl.dlq import BACKOFF_SCHEDULE, DLQWorker, DurableDLQ, _next_backoff
from scripts.crawl.pipeline import DLQRecord, InMemoryDLQ, PipelineStage

# ===========================================================================
# Backoff schedule (pure unit tests)
# ===========================================================================


class TestBackoff:
    def test_backoff_schedule(self):
        assert BACKOFF_SCHEDULE == [60, 300, 900]

    def test_next_backoff_first(self):
        assert _next_backoff(0) == 60

    def test_next_backoff_second(self):
        assert _next_backoff(1) == 300

    def test_next_backoff_third(self):
        assert _next_backoff(2) == 900

    def test_next_backoff_beyond_schedule(self):
        assert _next_backoff(10) == 3600
        assert _next_backoff(100) == 3600


# ===========================================================================
# DurableDLQ with mocked connection
# ===========================================================================


@pytest.fixture
def mock_conn():
    """Create a mock database connection."""
    return MagicMock()


@pytest.fixture
def dlq(mock_conn):
    """DurableDLQ with mocked connection."""
    d = DurableDLQ(conn_string="postgresql://test:test@127.0.0.1:5433/pncp_datalake")
    d._get_conn = MagicMock(return_value=mock_conn)
    return d


class TestDurableDLQ:
    """Tests for DurableDLQ using mocked DB connection."""

    @pytest.mark.asyncio
    async def test_push_calls_insert(self, dlq, mock_conn):
        """Given DLQRecord, when push called, then INSERT executed."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (42,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        record = DLQRecord(
            source="test-src",
            run_id="run-001",
            stage=PipelineStage.PARSE,
            raw_payload={"id": 1},
            error_code="parse_failed",
            error_message="Invalid JSON",
        )
        entry_id = await dlq.push(record)
        assert entry_id == 42

        # Verify INSERT was called
        insert_call = mock_cur.execute.call_args[0][0]
        assert "INSERT INTO dlq_entries" in insert_call
        assert "RETURNING id" in insert_call

    @pytest.mark.asyncio
    async def test_pending_count_queries(self, dlq, mock_conn):
        """Given DB returns count, when pending_count called, then correct count returned."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (7,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        count = await dlq.pending_count(source="test-src")
        assert count == 7

    @pytest.mark.asyncio
    async def test_pending_count_all_sources(self, dlq, mock_conn):
        """Given no filter, pending_count queries all sources."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (15,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        count = await dlq.pending_count()
        assert count == 15

    @pytest.mark.asyncio
    async def test_replay_returns_empty_when_no_pending(self, dlq, mock_conn):
        """Given no pending entries, replay returns empty list."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        records = await dlq.replay(source="test-src")
        assert len(records) == 0

    @pytest.mark.asyncio
    async def test_purge_called(self, dlq, mock_conn):
        """Given purge called, DELETE executed on dead/archived."""
        mock_cur = MagicMock()
        mock_cur.rowcount = 3
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        purged = await dlq.purge(source="test-src", older_than_days=30)
        assert purged == 3

        delete_call = mock_cur.execute.call_args[0][0]
        assert "DELETE FROM dlq_entries" in delete_call
        assert "dead" in delete_call
        assert "archived" in delete_call

    @pytest.mark.asyncio
    async def test_dead_count(self, dlq, mock_conn):
        """Given dead_count called, query for dead entries."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (2,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        dead = await dlq.dead_count(source="test-src")
        assert dead == 2

    @pytest.mark.asyncio
    async def test_push_handles_commit_failure(self, dlq, mock_conn):
        """Given commit failure, push raises and rolls back."""
        mock_conn.commit.side_effect = Exception("DB connection lost")

        record = DLQRecord(source="test", run_id="r1", stage=PipelineStage.PARSE, error_code="e", error_message="m")

        with pytest.raises(Exception, match="DB connection lost"):
            await dlq.push(record)
        mock_conn.rollback.assert_called_once()


# ===========================================================================
# DLQWorker using InMemoryDLQ (no DB needed)
# ===========================================================================


@pytest.mark.asyncio
async def test_worker_with_in_memory_dlq():
    """Given InMemoryDLQ with pending entries, worker processes them."""
    # Push records to InMemoryDLQ (not DurableDLQ)
    from scripts.crawl.pipeline import InMemoryDLQ as RealInMemoryDLQ
    dlq = RealInMemoryDLQ()

    # Use DurableDLQ's worker with InMemoryDLQ-compatible interface
    # Test the worker logic with the replay interface
    dlq.replay = AsyncMock(return_value=[
        DLQRecord(source="test", run_id="r1", stage=PipelineStage.PARSE, error_code="e", error_message="1")
    ])

    worker = DLQWorker(dlq, source="test", batch_size=10, interval=0.1, run_id="test-worker")
    count = await worker.run_once()
    assert count == 1
    assert worker._processed == 1


@pytest.mark.asyncio
async def test_worker_empty_queue():
    """Given empty queue, worker processes nothing."""
    dlq = InMemoryDLQ()
    dlq.replay = AsyncMock(return_value=[])

    worker = DLQWorker(dlq, source="test", batch_size=10, interval=0.1)
    count = await worker.run_once()
    assert count == 0
    assert worker._processed == 0


# ===========================================================================
# Pipeline + InMemoryDLQ integration (already tested in test_pipeline_fault.py)
# ===========================================================================


class TestDLQRecord:
    """DLQRecord dataclass creation tests."""

    def test_dlq_record_creation(self):
        rec = DLQRecord(
            source="pncp",
            run_id="r1",
            stage=PipelineStage.UPSERT,
            error_code="23505",
            error_message="unique violation",
        )
        assert rec.source == "pncp"
        assert rec.stage == PipelineStage.UPSERT
        assert rec.retry_count == 0
        assert rec.error_traceback == ""

    def test_dlq_record_with_traceback(self):
        rec = DLQRecord(
            source="test",
            run_id="r1",
            stage=PipelineStage.PARSE,
            error_code="e",
            error_message="err",
            error_traceback="Traceback...",
        )
        assert rec.error_traceback == "Traceback..."

    def test_dlq_record_all_stages(self):
        for stage in PipelineStage:
            rec = DLQRecord(source="t", run_id="r", stage=stage, error_code="e", error_message="m")
            assert rec.stage == stage
