"""Unit tests for scripts/crawl/checkpoint.py — sync psycopg2 functions.

Tests cover the four synchronous checkpoint operations used by
``orchestrator.py`` (TD-5.2):

  - is_crawl_completed_today
  - save_checkpoint
  - get_checkpoint
  - delete_checkpoint

All database interactions are mocked via ``unittest.mock.MagicMock``.
"""

from __future__ import annotations

import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# Pre-register supabase_client mock before importing checkpoint.py.
# The module imports supabase_client at the top level for its async
# functions (used by bids_crawler.py). Mocking it here isolates the
# sync-function tests from the missing supabase dependency.
if "supabase_client" not in sys.modules:
    sys.modules["supabase_client"] = MagicMock()
    sys.modules["supabase_client"].get_supabase = MagicMock()
    sys.modules["supabase_client"].sb_execute = MagicMock()

from scripts.crawl.checkpoint import (
    delete_checkpoint,
    get_checkpoint,
    is_crawl_completed_today,
    save_checkpoint,
)


# ===================================================================
# is_crawl_completed_today
# ===================================================================


class TestIsCrawlCompletedToday:
    """is_crawl_completed_today(conn, source, scope_key="default")"""

    def test_returns_true_when_checkpoint_exists(self):
        """Returns True when a row with last_date = CURRENT_DATE is found."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = (1,)

        result = is_crawl_completed_today(conn, "pncp", "default")

        assert result is True
        cursor.execute.assert_called_once()
        conn.cursor.assert_called_once()
        cursor.close.assert_called_once()

    def test_returns_false_when_no_checkpoint(self):
        """Returns False when no matching row exists."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = None

        result = is_crawl_completed_today(conn, "pncp", "default")

        assert result is False

    def test_uses_default_scope_key(self):
        """Uses scope_key='default' when not explicitly provided."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = (1,)

        result = is_crawl_completed_today(conn, "dom_sc")

        assert result is True
        call_args = cursor.execute.call_args[0]
        assert call_args[1] == ("dom_sc", "default")

    def test_returns_false_on_database_error(self):
        """Returns False and logs a warning when the query raises."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.execute.side_effect = Exception("connection lost")

        with patch("scripts.crawl.checkpoint.logger") as mock_logger:
            result = is_crawl_completed_today(conn, "pncp", "default")

        assert result is False
        mock_logger.warning.assert_called_once()


# ===================================================================
# save_checkpoint (sync)
# ===================================================================


class TestSaveCheckpoint:
    """save_checkpoint(conn, source, scope_key, last_date, records_fetched)"""

    def test_upserts_checkpoint(self):
        """Executes INSERT ... ON CONFLICT with the provided values."""
        conn = MagicMock()
        cursor = conn.cursor.return_value

        save_checkpoint(
            conn,
            source="pncp",
            scope_key="default",
            last_date=date(2026, 7, 11),
            records_fetched=142,
        )

        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args[0]
        sql = call_args[0]
        params = call_args[1]
        assert "ON CONFLICT" in sql.upper() or "ON CONFLICT" in sql
        assert params[0] == "pncp"
        assert params[1] == "default"
        assert params[2] == date(2026, 7, 11)
        assert params[3] == 142
        conn.commit.assert_called_once()
        cursor.close.assert_called_once()

    def test_defaults_last_date_to_today(self):
        """Uses date.today() when last_date is not provided."""
        conn = MagicMock()
        cursor = conn.cursor.return_value

        save_checkpoint(conn, source="pncp")

        call_args = cursor.execute.call_args[0]
        params = call_args[1]
        assert params[2] == date.today()

    def test_defaults_records_fetched_to_zero(self):
        """Uses 0 when records_fetched is not provided."""
        conn = MagicMock()
        cursor = conn.cursor.return_value

        save_checkpoint(conn, source="pncp", last_date=date(2026, 7, 11))

        call_args = cursor.execute.call_args[0]
        assert call_args[1][3] == 0

    def test_raises_on_database_error(self):
        """Raises the original exception when the upsert fails."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.execute.side_effect = Exception("disk full")

        with pytest.raises(Exception, match="disk full"):
            save_checkpoint(conn, source="pncp")


# ===================================================================
# get_checkpoint
# ===================================================================


class TestGetCheckpoint:
    """get_checkpoint(conn, source, scope_key="default")"""

    def test_returns_checkpoint_dict_when_found(self):
        """Returns a dict with all ingestion_checkpoints columns."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = (
            "pncp",          # source
            "default",       # scope_key
            0,               # last_page
            date(2026, 7, 11),  # last_date
            None,            # last_id
            142,             # records_fetched
            "2026-07-11 10:00:00",  # updated_at
        )

        result = get_checkpoint(conn, "pncp", "default")

        assert result is not None
        assert result["source"] == "pncp"
        assert result["scope_key"] == "default"
        assert result["last_date"] == date(2026, 7, 11)
        assert result["records_fetched"] == 142

    def test_returns_none_when_not_found(self):
        """Returns None when no checkpoint exists for the given key."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchone.return_value = None

        result = get_checkpoint(conn, "pncp", "default")

        assert result is None

    def test_returns_none_on_database_error(self):
        """Returns None and logs a warning when the query raises."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.execute.side_effect = Exception("timeout")

        with patch("scripts.crawl.checkpoint.logger") as mock_logger:
            result = get_checkpoint(conn, "pncp", "default")

        assert result is None
        mock_logger.warning.assert_called_once()


# ===================================================================
# delete_checkpoint
# ===================================================================


class TestDeleteCheckpoint:
    """delete_checkpoint(conn, source, scope_key="default")"""

    def test_returns_true_when_deleted(self):
        """Returns True when a row was actually deleted."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.rowcount = 1

        result = delete_checkpoint(conn, "pncp", "default")

        assert result is True
        cursor.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_returns_false_when_not_found(self):
        """Returns False when no row matched the delete."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.rowcount = 0

        result = delete_checkpoint(conn, "pncp", "default")

        assert result is False

    def test_uses_correct_parameters(self):
        """Passes (source, scope_key) as query parameters."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.rowcount = 1

        delete_checkpoint(conn, "dom_sc", "default")

        call_args = cursor.execute.call_args[0]
        assert call_args[1] == ("dom_sc", "default")

    def test_returns_false_on_database_error(self):
        """Returns False and logs a warning when the delete raises."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.execute.side_effect = Exception("permission denied")

        with patch("scripts.crawl.checkpoint.logger") as mock_logger:
            result = delete_checkpoint(conn, "pncp", "default")

        assert result is False
        mock_logger.warning.assert_called_once()
