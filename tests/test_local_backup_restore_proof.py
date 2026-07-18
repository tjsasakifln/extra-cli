"""Unit tests for DSN helpers in local_backup_restore_proof (no live PG required)."""
from __future__ import annotations

from scripts.ops.local_backup_restore_proof import _dsn_with_db, _parse_dsn


def test_parse_dsn() -> None:
    p = _parse_dsn("postgresql://test:secret@127.0.0.1:5433/extra_test")
    assert p["user"] == "test"
    assert p["host"] == "127.0.0.1"
    assert p["port"] == "5433"
    assert p["dbname"] == "extra_test"


def test_dsn_with_db_swaps_database() -> None:
    p = _parse_dsn("postgresql://u:p@localhost:5432/src")
    d = _dsn_with_db(p, "extra_restore_proof")
    assert d.endswith("/extra_restore_proof")
    assert "localhost" in d
