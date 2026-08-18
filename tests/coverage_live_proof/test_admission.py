"""Unit tests for DSN admission, fake-connection refusal, sanitize, threshold."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.coverage.dual_capability_coverage import GATE_THRESHOLD
from scripts.ops.coverage_live_proof import EVIDENCE_SCHEMA_VERSION
from scripts.ops.coverage_live_proof.admission import (
    production_hits,
    read_gate_threshold,
    refuse_non_postgres_scheme,
    refuse_production_dsn,
    require_explicit_dsn,
    sanitize_dsn,
    sanitize_text,
)
from scripts.ops.coverage_live_proof.errors import (
    FakeConnectionError,
    MissingDsnError,
    NotPostgresError,
    ProductionDsnError,
)
from scripts.ops.coverage_live_proof.evidence import (
    normalize_evidence,
    semantic_hash,
    write_evidence_pack,
)
from scripts.ops.coverage_live_proof.probe import (
    assert_real_postgres,
    connect_real,
    is_postgres_version,
)
from scripts.ops.coverage_live_proof.runner import resolve_cli_dsn


def test_refuses_missing_dsn() -> None:
    with pytest.raises(MissingDsnError, match="explicit DSN"):
        require_explicit_dsn(None)
    with pytest.raises(MissingDsnError, match="explicit DSN"):
        require_explicit_dsn("   ")
    assert require_explicit_dsn("postgresql://test:test@127.0.0.1:5433/extra_test")


def test_refuses_production_host_and_base() -> None:
    cases = (
        "postgresql://u:secret@ec-prod:5432/extra",
        "postgresql://u:p@ec-prod.example:5432/extra",
        "postgresql://u:p@127.0.0.1:5432/extra_prod",
        "postgresql://u:p@host/x?app=/opt/extra-consultoria/app",
        "postgresql://u:p@vps.example/production",
    )
    for dsn in cases:
        with pytest.raises(ProductionDsnError, match="production DSN refused"):
            refuse_production_dsn(dsn)
    assert production_hits("postgresql://test:test@127.0.0.1:5433/extra_test") == []
    refuse_production_dsn("postgresql://test:test@127.0.0.1:5433/extra_test")


def test_refuses_sqlite_and_non_postgres_scheme() -> None:
    with pytest.raises(NotPostgresError, match="SQLite"):
        refuse_non_postgres_scheme("sqlite:///tmp/proof.db")
    with pytest.raises(NotPostgresError):
        refuse_non_postgres_scheme("sqlite3://foo")
    refuse_non_postgres_scheme("postgresql://test:test@127.0.0.1:5433/extra_test")
    assert is_postgres_version("PostgreSQL 16.4 on x86_64") is True
    assert is_postgres_version("SQLite 3.45.0") is False


def test_assert_real_postgres_refuses_magicmock() -> None:
    fake = MagicMock(name="psycopg2.extensions.connection")
    fake.cursor.return_value.fetchone.return_value = ("PostgreSQL 16.0", "16.0")
    with pytest.raises(FakeConnectionError, match="MagicMock"):
        assert_real_postgres(fake)


def test_assert_real_postgres_refuses_sqlite_version() -> None:
    class _Cursor:
        def execute(self, _sql: str) -> None:
            return None

        def fetchone(self) -> tuple[str, str]:
            return ("SQLite 3.45.1", "3.45.1")

        def close(self) -> None:
            return None

    class _ForeignConn:
        def cursor(self) -> _Cursor:
            return _Cursor()

    with pytest.raises(NotPostgresError, match="not PostgreSQL"):
        assert_real_postgres(_ForeignConn())


def test_connect_real_refuses_mocked_psycopg2() -> None:
    """Autouse fixture mocks psycopg2.connect — the shipped probe must refuse it."""
    with pytest.raises(FakeConnectionError):
        connect_real("postgresql://test:test@127.0.0.1:5433/extra_test")


def test_sanitize_dsn_and_logs_hide_password() -> None:
    dsn = "postgresql://proof:super-secret@127.0.0.1:5432/coverage_live_proof"
    safe = sanitize_dsn(dsn)
    assert "super-secret" not in safe
    assert "***" in safe
    assert "127.0.0.1" in safe
    leaked = f"failed to connect {dsn} password=super-secret"
    cleaned = sanitize_text(leaked, dsn)
    assert "super-secret" not in cleaned
    assert dsn not in cleaned


def test_threshold_is_read_not_rewritten() -> None:
    assert read_gate_threshold() == GATE_THRESHOLD
    assert GATE_THRESHOLD == 0.95
    package = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "coverage_live_proof"
    for path in package.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "GATE_THRESHOLD =" not in text
        assert "threshold = 0.95" not in text.lower()


def test_normalized_hash_stable_across_volatile_fields(tmp_path: Path) -> None:
    base = {
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "source_wide_count": 1,
        "entity_scoped_count": 1,
        "threshold": read_gate_threshold(),
        "scenarios": {"A": {"reason": "source_wide_aggregate_without_identity"}},
    }
    first = {**base, "run_id": "local-aaa", "duration_ms": 12, "generated_at": "2026-01-01T00:00:00Z"}
    second = {**base, "run_id": "local-bbb", "duration_ms": 99, "generated_at": "2026-12-31T23:59:59Z"}
    assert semantic_hash(normalize_evidence(first)) == semantic_hash(normalize_evidence(second))
    pack_a = write_evidence_pack(tmp_path / "a", first)
    pack_b = write_evidence_pack(tmp_path / "b", second)
    assert pack_a["normalized_semantic_hash"] == pack_b["normalized_semantic_hash"]
    bytes_a = (tmp_path / "a" / "evidence.normalized.json").read_bytes()
    bytes_b = (tmp_path / "b" / "evidence.normalized.json").read_bytes()
    assert bytes_a == bytes_b


def test_resolve_cli_dsn_does_not_invent_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    assert resolve_cli_dsn(None) is None
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    assert resolve_cli_dsn(None) == "postgresql://test:test@127.0.0.1:5433/extra_test"
    assert resolve_cli_dsn("postgresql://x:y@127.0.0.1/db") == "postgresql://x:y@127.0.0.1/db"


def test_cli_run_without_dsn_exits_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    from scripts.ops.coverage_live_proof.__main__ import main

    code = main(["run", "--output", str(tmp_path)])
    assert code != 0
