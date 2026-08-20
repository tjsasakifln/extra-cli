"""Migration pairing and opt-in real Postgres persist/SELECT."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.models import NationalCoverageError
from scripts.national_coverage.store import REQUIRED_TABLES, persist_coverage, select_consumer_answer
from scripts.testing.real_db_guard import canonical_dsn, dsn_is_reachable

MIGRATION = Path("db/migrations/097_national_coverage.sql")
ROLLBACK = Path("db/rollback/097_national_coverage_rollback.sql")


def test_migration_files_exist_and_are_paired() -> None:
    assert MIGRATION.is_file()
    assert ROLLBACK.is_file()
    up = MIGRATION.read_text(encoding="utf-8")
    down = ROLLBACK.read_text(encoding="utf-8")
    for table in REQUIRED_TABLES:
        assert table in up
        assert table in down
    assert "national_coverage_consumer_v1" in up
    assert "SELECT-only" in up or "SELECT-only" in down or "editorial" in up
    assert "extra_1093" in up


def test_persist_refuses_magic_mock() -> None:
    payload = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    with pytest.raises(NationalCoverageError, match="MagicMock"):
        persist_coverage(MagicMock(), payload)
    with pytest.raises(NationalCoverageError, match="MagicMock"):
        select_consumer_answer(
            MagicMock(),
            universe_id="x",
            geography="BR",
            period="2026",
            source="pncp",
            grain="publishing_org",
        )


def _connect(dsn: str):
    import psycopg2

    return psycopg2.connect(dsn, connect_timeout=3)


def _exec_sql(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().upper().startswith("SET LOCAL"))
    with conn.cursor() as cursor:
        cursor.execute(sql)


@pytest.mark.real_db
def test_persist_and_select_on_real_postgres() -> None:
    if not dsn_is_reachable():
        pytest.skip("LOCAL_DATALAKE_DSN not reachable")
    payload = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    conn = _connect(canonical_dsn())
    try:
        _exec_sql(conn, MIGRATION)
        persist_coverage(conn, payload)
        row = select_consumer_answer(
            conn,
            universe_id=payload["national_universe_id"],
            geography=payload["consumer"]["requested_geography"],
            period=payload["consumer"]["requested_period"],
            source=payload["consumer"]["requested_source"],
            grain=payload["consumer"]["requested_grain"],
        )
        conn.rollback()
    finally:
        conn.close()
    assert row is not None
    assert row["universe_id"] == payload["national_universe_id"]
    assert row["national_claim_authorized"] is False
    assert row["verdict"] == payload["verdict"]
    assert row["content_hash"] == payload["consumer"]["content_hash"]
