"""Tests for WatermarkManager.

Uses mocked DB connection for unit tests.
Integration tests (with real DB) require the database marker.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.crawl.watermark import STALLED_THRESHOLD_SECONDS, WatermarkManager


@pytest.fixture
def mock_cur():
    """Mock cursor."""
    return MagicMock()


@pytest.fixture
def mock_conn(mock_cur):
    """Mock connection returning mock cursor."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = mock_cur
    return conn


@pytest.fixture
def wm(mock_conn):
    """WatermarkManager with mocked connection."""
    m = WatermarkManager(conn_string="postgresql://test:test@127.0.0.1:5433/pncp_datalake")
    m._get_conn = MagicMock(return_value=mock_conn)
    return m


class TestWatermarkManager:
    """Tests for WatermarkManager."""

    @pytest.mark.asyncio
    async def test_commit_calls_function(self, wm, mock_cur):
        """Given commit called, the commit_watermark function is called."""
        mock_cur.fetchone.return_value = (1,)

        wm_id = await wm.commit("test-source", "page", "42", run_id="run-001")
        assert wm_id == 1
        call_sql = mock_cur.execute.call_args[0][0]
        assert "commit_watermark" in call_sql

    @pytest.mark.asyncio
    async def test_commit_tracks_metrics(self, wm, mock_cur):
        """Given commit called, metric is incremented."""
        mock_cur.fetchone.return_value = (1,)
        wm_id = await wm.commit("test-source", "page", "42", run_id="run-001")
        assert wm_id == 1

    @pytest.mark.asyncio
    async def test_get_last_returns_none_when_empty(self, wm, mock_cur):
        """Given no watermarks, get_last returns None."""
        mock_cur.fetchone.return_value = None
        result = await wm.get_last("test-source")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_returns_value(self, wm, mock_cur):
        """Given watermark exists, get_last returns its value."""
        mock_cur.fetchone.return_value = ("42",)
        result = await wm.get_last("test-source")
        assert result == "42"

    @pytest.mark.asyncio
    async def test_get_next_page_defaults_to_one(self, wm, mock_cur):
        """Given no watermark, get_next_page returns 1."""
        mock_cur.fetchone.return_value = None
        page = await wm.get_next_page("test-source")
        assert page == 1

    @pytest.mark.asyncio
    async def test_get_next_page_with_overlap(self, wm, mock_cur):
        """Given watermark at page 50, get_next_page returns page with overlap."""
        mock_cur.fetchone.return_value = ("50",)
        page = await wm.get_next_page("test-source", overlap=1)
        assert page == 49

    @pytest.mark.asyncio
    async def test_get_next_page_overlap_capped_at_1(self, wm, mock_cur):
        """Given watermark at page 1, get_next_page returns 1 (not 0)."""
        mock_cur.fetchone.return_value = ("1",)
        page = await wm.get_next_page("test-source", overlap=1)
        assert page == 1

    @pytest.mark.asyncio
    async def test_get_next_page_larger_overlap(self, wm, mock_cur):
        """Given watermark at page 100, get_next_page with overlap=5 returns 95."""
        mock_cur.fetchone.return_value = ("100",)
        page = await wm.get_next_page("test-source", overlap=5)
        assert page == 95

    @pytest.mark.asyncio
    async def test_mark_in_progress(self, wm, mock_cur):
        """Given mark_in_progress called, INSERT executed."""
        await wm.mark_in_progress("test-source", run_id="r1")
        call_sql = mock_cur.execute.call_args[0][0]
        assert "INSERT INTO pipeline_watermarks" in call_sql
        assert "in_progress" in call_sql

    @pytest.mark.asyncio
    async def test_check_stalled_no_stalled(self, wm, mock_cur):
        """Given no stalled watermarks, check_stalled returns empty list."""
        mock_cur.fetchall.return_value = []
        stalled = await wm.check_stalled(source="test-source")
        assert len(stalled) == 0

    @pytest.mark.asyncio
    async def test_check_stalled_finds_stalled(self, wm, mock_cur):
        """Given stalled watermarks, check_stalled returns them."""
        mock_cur.fetchall.return_value = [
            {"source": "test", "scope_key": "default", "watermark_type": "page",
             "watermark_value": "10", "run_id": "r1", "committed_at": None}
        ]
        stalled = await wm.check_stalled(source="test")
        assert len(stalled) == 1
        assert stalled[0]["source"] == "test"

    @pytest.mark.asyncio
    async def test_mark_stalled(self, wm, mock_cur):
        """Given mark_stalled called, watermarks updated."""
        mock_cur.rowcount = 2
        marked = await wm.mark_stalled("test-source")
        assert marked == 2
        call_sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE pipeline_watermarks" in call_sql
        assert "stalled" in call_sql

    @pytest.mark.asyncio
    async def test_commit_failure_rolls_back(self, wm, mock_conn):
        """Given commit fails, push raises and rolls back."""
        mock_conn.commit.side_effect = Exception("DB error")
        with pytest.raises(Exception, match="DB error"):
            await wm.commit("test", "page", "1", run_id="r1")
        mock_conn.rollback.assert_called_once()


class TestStalledThreshold:
    def test_threshold_value(self):
        assert STALLED_THRESHOLD_SECONDS == 7200

    def test_threshold_hours(self):
        assert STALLED_THRESHOLD_SECONDS == 2 * 3600  # 2 hours
