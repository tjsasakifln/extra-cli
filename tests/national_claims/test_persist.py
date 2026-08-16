"""Migration up/down and persist/replay on real PostgreSQL when DSN is present."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.national_claims.gate import decide
from scripts.national_claims.loader import request_from_dict
from scripts.national_claims.preflight import REQUIRED_TABLES, inspect_national_claims_schema, probe_national_claims
from scripts.national_claims.sample_fixtures import fixture_authorized_national, fixture_source_wide_only
from scripts.national_claims.store import invalidate_lkg, persist_decision, replay_decision
from scripts.testing.connection_policy import connection_kind

MIGRATION = Path("db/migrations/096_national_claims_gate.sql")
ROLLBACK = Path("db/rollback/096_national_claims_gate_rollback.sql")


def _connect(dsn: str):
    import psycopg2

    return psycopg2.connect(dsn, connect_timeout=3)


def _exec_sql(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().upper().startswith("SET LOCAL"))
    with conn.cursor() as cursor:
        cursor.execute(sql)


def test_migration_files_exist_and_are_paired() -> None:
    assert MIGRATION.is_file()
    assert ROLLBACK.is_file()
    up = MIGRATION.read_text(encoding="utf-8")
    down = ROLLBACK.read_text(encoding="utf-8")
    for table in REQUIRED_TABLES:
        assert table in up
        assert table in down
    assert "096 was free on origin/main" in up
    assert "DROP TABLE IF EXISTS public.national_claims_universe" in down


def test_persist_replay_and_rollback_on_real_postgres() -> None:
    dsn = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    required = os.environ.get("REQUIRE_REAL_DB", "").strip().lower() in {"1", "true", "yes"}
    if not dsn:
        if required:
            pytest.fail("REQUIRE_REAL_DB=1 but LOCAL_DATALAKE_DSN is absent")
        pytest.skip("LOCAL_DATALAKE_DSN absent: explicit skip before business SQL")
    try:
        conn = _connect(dsn)
    except Exception as exc:
        if required:
            pytest.fail(f"required DSN not reachable: {type(exc).__name__}")
        pytest.skip(f"database unreachable: {exc}")
    kind = connection_kind(conn)
    assert kind != "MagicMock"
    try:
        conn.autocommit = True
        _exec_sql(conn, MIGRATION)
        missing = inspect_national_claims_schema(conn)
        assert missing == ()
        preflight = probe_national_claims(dsn, require_real=False, opener=lambda *_a, **_k: _connect(dsn))
        assert preflight["outcome"] == "ready"

        request = request_from_dict(fixture_authorized_national())
        payload = decide(request)
        persist_decision(conn, request, payload)
        replayed = replay_decision(conn, payload["claim_id"])
        assert replayed["content_hash"] == payload["content_hash"]
        assert replayed["authorization_state"] == payload["authorization_state"]
        assert replayed["national_universe_id"] == payload["national_universe_id"]

        wide_request = request_from_dict(fixture_source_wide_only())
        wide_payload = decide(wide_request)
        persist_decision(conn, wide_request, wide_payload)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT identity_class FROM national_claims_aggregate_evidence WHERE claim_id = %s",
                (wide_payload["claim_id"],),
            )
            classes = [row[0] for row in cursor.fetchall()]
        assert "SOURCE_WIDE_AGGREGATE" in classes
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM national_claims_identity_evidence WHERE claim_id = %s",
                (wide_payload["claim_id"],),
            )
            assert cursor.fetchone()[0] == 0

        stamped = invalidate_lkg(
            conn,
            national_universe_id=payload["national_universe_id"],
            reason="universe_hash_change",
            as_of="2026-08-16T00:00:00Z",
        )
        assert stamped >= 0
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM national_claims_lkg WHERE claim_id = %s",
                (payload["claim_id"],),
            )
            assert cursor.fetchone()[0] >= 1

        _exec_sql(conn, ROLLBACK)
        missing_after = inspect_national_claims_schema(conn)
        assert set(missing_after) == set(REQUIRED_TABLES)
        _exec_sql(conn, MIGRATION)
    finally:
        conn.close()
