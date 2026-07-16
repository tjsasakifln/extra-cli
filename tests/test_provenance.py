"""Tests for ProvenanceTracker, DedupChecker, and FreshnessChecker.

Uses mocked DB connection for unit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl.provenance import (
    DEFAULT_SLA_HOURS,
    SOURCE_SLA,
    DedupChecker,
    FreshnessChecker,
    ProvenanceTracker,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_cur():
    return MagicMock()


@pytest.fixture
def mock_conn(mock_cur):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = mock_cur
    return conn


@pytest.fixture
def tracker(mock_conn):
    t = ProvenanceTracker(conn_string="postgresql://test:test@127.0.0.1:5433/pncp_datalake")
    t._get_conn = MagicMock(return_value=mock_conn)
    return t


@pytest.fixture
def dedup(mock_conn):
    d = DedupChecker(conn_string="postgresql://test:test@127.0.0.1:5433/pncp_datalake")
    d._get_conn = MagicMock(return_value=mock_conn)
    return d


# ===========================================================================
# ProvenanceTracker
# ===========================================================================


class TestProvenanceTracker:
    @pytest.mark.asyncio
    async def test_start_run(self, tracker, mock_cur):
        """Given start_run called, INSERT executed."""
        await tracker.start_run("run-001", "pncp", mode="full")
        call_sql = mock_cur.execute.call_args[0][0]
        assert "INSERT INTO pipeline_runs" in call_sql
        assert "running" in call_sql

    @pytest.mark.asyncio
    async def test_start_run_with_params(self, tracker, mock_cur):
        """Given start_run with period params, they are included."""
        await tracker.start_run(
            "run-002", "pcp", mode="incremental",
            params={"uf": "SC"}, period_start="2026-01-01", period_end="2026-07-16",
        )
        call_sql = mock_cur.execute.call_args[0][0]
        assert "INSERT INTO pipeline_runs" in call_sql
        # Verify params are passed as arguments (not embedded in SQL)
        call_args = mock_cur.execute.call_args[0]
        assert "run-002" in str(call_args)
        assert "pcp" in str(call_args)
        assert "incremental" in str(call_args)

    @pytest.mark.asyncio
    async def test_complete_run(self, tracker, mock_cur):
        """Given complete_run called, UPDATE with stats."""
        await tracker.complete_run(
            "run-001",
            records_fetched=100,
            records_upserted=95,
            records_dlq=3,
            pages_completed=10,
            duration_ms=5000,
        )
        call_sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE pipeline_runs" in call_sql
        assert "completed" in call_sql

    @pytest.mark.asyncio
    async def test_fail_run(self, tracker, mock_cur):
        """Given fail_run called, UPDATE with error."""
        await tracker.fail_run("run-001", error_message="Connection timeout")
        call_sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE pipeline_runs" in call_sql
        assert "failed" in call_sql
        assert "Connection timeout" in str(mock_cur.execute.call_args[0])

    @pytest.mark.asyncio
    async def test_get_run_found(self, tracker, mock_cur):
        """Given run exists, get_run returns it."""
        mock_cur.fetchone.return_value = {"run_id": "run-001", "source": "pncp", "status": "completed"}
        run = await tracker.get_run("run-001")
        assert run is not None
        assert run["run_id"] == "run-001"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, tracker, mock_cur):
        """Given no such run, get_run returns None."""
        mock_cur.fetchone.return_value = None
        run = await tracker.get_run("nonexistent")
        assert run is None

    @pytest.mark.asyncio
    async def test_get_latest_run(self, tracker, mock_cur):
        """Given source with runs, get_latest_run returns most recent."""
        mock_cur.fetchone.return_value = {"run_id": "run-005", "source": "pncp", "status": "completed"}
        latest = await tracker.get_latest_run("pncp")
        assert latest is not None
        assert latest["run_id"] == "run-005"

    @pytest.mark.asyncio
    async def test_start_run_rollback_on_failure(self, tracker, mock_conn, mock_cur):
        """Given DB error, start_run rolls back."""
        mock_cur.execute.side_effect = Exception("connection lost")
        with pytest.raises(Exception, match="connection lost"):
            await tracker.start_run("run-001", "pncp")
        mock_conn.rollback.assert_called_once()


# ===========================================================================
# DedupChecker
# ===========================================================================


class TestDedupChecker:
    def test_compute_hash_deterministic(self):
        """Given same data, compute_hash returns same hash."""
        data = {"id": 1, "name": "test", "value": 42.5}
        h1 = DedupChecker.compute_hash(data)
        h2 = DedupChecker.compute_hash(data)
        assert h1 == h2

    def test_compute_hash_changes_with_data(self):
        """Given different data, compute_hash returns different hash."""
        h1 = DedupChecker.compute_hash({"a": 1, "b": 2})
        h2 = DedupChecker.compute_hash({"a": 1, "b": 3})
        assert h1 != h2

    def test_compute_hash_sorted_keys(self):
        """Given same data with different key order, hash is same."""
        h1 = DedupChecker.compute_hash({"b": 2, "a": 1})
        h2 = DedupChecker.compute_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_compute_hash_returns_hex(self):
        """Given data, compute_hash returns hex string."""
        h = DedupChecker.compute_hash({"test": "data"})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)

    @pytest.mark.asyncio
    async def test_is_duplicate_true(self, dedup, mock_cur):
        """Given hash exists, is_duplicate returns True."""
        mock_cur.fetchone.return_value = (1,)
        assert await dedup.is_duplicate("abc123") is True

    @pytest.mark.asyncio
    async def test_is_duplicate_false(self, dedup, mock_cur):
        """Given hash does not exist, is_duplicate returns False."""
        mock_cur.fetchone.return_value = None
        assert await dedup.is_duplicate("nonexistent") is False

    @pytest.mark.asyncio
    async def test_record_new_hash(self, dedup, mock_cur):
        """Given new content hash, record inserts it and returns True."""
        mock_cur.fetchone.return_value = (1,)  # seen_count = 1
        is_new = await dedup.record("hash123", "pncp", "run-001")
        assert is_new is True

    @pytest.mark.asyncio
    async def test_record_existing_hash(self, dedup, mock_cur):
        """Given existing content hash, record updates it and returns False."""
        mock_cur.fetchone.return_value = (2,)  # seen_count = 2
        is_new = await dedup.record("hash123", "pncp", "run-002")
        assert is_new is False


# ===========================================================================
# FreshnessChecker
# ===========================================================================


class TestFreshnessChecker:
    def test_sla_hours_default(self):
        """Given unknown source, get_sla_hours returns default."""
        checker = FreshnessChecker(MagicMock())
        assert checker.get_sla_hours("unknown_source") == DEFAULT_SLA_HOURS

    def test_sla_hours_known(self):
        """Given known source, get_sla_hours returns its SLA."""
        checker = FreshnessChecker(MagicMock())
        assert checker.get_sla_hours("pncp") == 24
        assert checker.get_sla_hours("pcp") == 48
        assert checker.get_sla_hours("ciga_ckan") == 168

    def test_source_sla_defined_for_all_sources(self):
        """Given all known sources, SLA is defined for each."""
        expected_sources = [
            "pncp", "pcp", "compras_gov", "ciga_ckan", "tce_sc",
            "doe_sc", "dom_sc", "sc_compras", "contracts",
            "transparencia", "mides_bigquery",
        ]
        for src in expected_sources:
            assert src in SOURCE_SLA, f"Missing SLA for {src}"

    @pytest.mark.asyncio
    async def test_is_fresh_no_latest_run(self):
        """Given source with no runs, is_fresh returns False."""
        tracker = MagicMock()
        # get_latest_run is async, so we need an async return value
        async def mock_none(*args, **kwargs):
            return None
        tracker.get_latest_run = mock_none
        checker = FreshnessChecker(tracker)
        is_fresh, latest = await checker.is_fresh("pncp")
        assert is_fresh is False
        assert latest is None

    @pytest.mark.asyncio
    async def test_get_freshness_report(self):
        """Given sources, get_freshness_report returns report dict."""
        tracker = MagicMock()

        async def mock_get_latest(source):
            if source == "pncp":
                return {"run_id": "r1", "completed_at": None}
            return None

        tracker.get_latest_run = mock_get_latest
        checker = FreshnessChecker(tracker)
        report = await checker.get_freshness_report(sources=["pncp", "unknown"])
        assert "pncp" in report
        assert "unknown" in report
        assert report["pncp"]["status"] in ("fresh", "stale", "never_crawled")
        assert report["unknown"]["status"] == "never_crawled"
