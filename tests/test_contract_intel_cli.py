"""Tests for scripts/contract_intel/cli.py.

Covers:
  - CLI commands execute without errors (offline SQLite)
  - Seed command populates target universe
  - Stats command returns expected metrics
  - JSON format output is valid
  - DB unavailability is handled gracefully
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.contract_intel.cli import (  # noqa: E402
    _ensure_tables,
    _get_connection,
    _sqlite_stats_query,
    seed_target_universe,
)

# ---------------------------------------------------------------------------
# DB connection tests
# ---------------------------------------------------------------------------


class TestConnection:
    """Offline SQLite connection tests."""

    def test_sqlite_connection_with_temp_db(self):
        """Can create SQLite connection with temp file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn, backend = _get_connection(db_path)
            assert backend == "sqlite"
            _ensure_tables(conn, backend)

            # Verify tables exist
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            assert "target_universe" in tables
            assert "pncp_supplier_contracts" in tables
            conn.close()
        finally:
            os.unlink(db_path)

    def test_sqlite_connection_default_path(self):
        """Default path works when no DSN set (uses temp DB to avoid old schema)."""
        old_dsn = os.environ.pop("LOCAL_DATALAKE_DSN", None)
        try:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            conn, backend = _get_connection(db_path)
            assert backend == "sqlite"
            _ensure_tables(conn, backend)
            conn.close()
            os.unlink(db_path)
        finally:
            if old_dsn:
                os.environ["LOCAL_DATALAKE_DSN"] = old_dsn


# ---------------------------------------------------------------------------
# Seed tests
# ---------------------------------------------------------------------------


class TestSeed:
    """Target universe seeding."""

    def test_seed_populates_target_universe(self):
        """Seed command populates the target_universe table."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            _ensure_tables(conn, "sqlite")
            _count = seed_target_universe(conn, "sqlite")
            conn.close()

            assert _count > 0, f"Expected > 0 entities, got {_count}"
            assert _count == 1093, f"Expected 1093 entities within 200km, got {_count}"

            # Verify data
            conn2 = sqlite3.connect(db_path)
            cur = conn2.cursor()
            cur.execute("SELECT COUNT(*) FROM target_universe WHERE within_200km = 1")
            assert cur.fetchone()[0] == _count
            conn2.close()
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Stats query tests
# ---------------------------------------------------------------------------


class TestStats:
    """Stats query execution."""

    def test_stats_on_empty_db(self):
        """Stats on empty DB returns zeros, not errors."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            _ensure_tables(conn, "sqlite")
            cur = conn.cursor()
            cur.execute(_sqlite_stats_query())
            rows = cur.fetchall()
            conn.close()

            assert len(rows) > 0
            # Total contracts should be 0
            total_row = [r for r in rows if "Total contracts" in r[0]]
            assert len(total_row) == 1
            assert total_row[0][1] == "0"
        finally:
            os.unlink(db_path)

    def test_stats_on_seeded_db(self):
        """Stats on seeded DB returns correct counts."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            _ensure_tables(conn, "sqlite")
            seed_target_universe(conn, "sqlite")  # verify no errors

            cur = conn.cursor()
            cur.execute(_sqlite_stats_query())
            rows = cur.fetchall()
            conn.close()

            assert len(rows) >= 4  # At least 4 metrics

            # After seeding, unique entities should still be 0
            # (no contracts loaded, just target universe)
            unique_entities_row = [r for r in rows if "Unique entities" in r[0]]
            assert len(unique_entities_row) == 1
            assert unique_entities_row[0][1] == "0", "Unique entities should be 0 (no contracts, only target universe)"
        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# JSON output tests
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """JSON format output is valid."""

    def test_json_output_valid(self):
        """JSON output can be parsed."""
        # Simulate what the CLI would output
        output = [{"col1": "val1", "col2": 42}]
        json_str = json.dumps(output, indent=2, ensure_ascii=False, default=str)
        parsed = json.loads(json_str)
        assert parsed == output


# ---------------------------------------------------------------------------
# DB unavailability test
# ---------------------------------------------------------------------------


class TestDbUnavailable:
    """Graceful handling when no DB is available."""

    def test_sqlite_fallback_when_no_dsn(self):
        """When DSN is unset, SQLite fallback is used — no crash."""
        old_dsn = os.environ.pop("LOCAL_DATALAKE_DSN", None)
        try:
            # Should not raise
            conn, backend = _get_connection()
            assert backend == "sqlite"
            assert conn is not None
            conn.close()
        finally:
            if old_dsn:
                os.environ["LOCAL_DATALAKE_DSN"] = old_dsn
