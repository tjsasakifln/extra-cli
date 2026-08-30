"""Migration pairing and opt-in real Postgres persist/SELECT."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.models import NationalCoverageError
from scripts.national_coverage.store import REQUIRED_TABLES, persist_coverage, select_consumer_answer
from scripts.testing.real_db_guard import admit_real_db_or_raise, canonical_dsn

MIGRATION = Path("db/migrations/097_national_coverage.sql")
ROLLBACK = Path("db/rollback/097_national_coverage_rollback.sql")
MIGRATION_SELECT_ONLY = Path("db/migrations/098_national_coverage_consumer_select_only.sql")
ROLLBACK_SELECT_ONLY = Path("db/rollback/098_national_coverage_consumer_select_only_rollback.sql")
MIGRATION_NULLABLE_UNITS = Path("db/migrations/102_national_coverage_nullable_expected_units.sql")
ROLLBACK_NULLABLE_UNITS = Path("db/rollback/102_national_coverage_nullable_expected_units_rollback.sql")


def test_migration_files_exist_and_are_paired() -> None:
    assert MIGRATION.is_file()
    assert ROLLBACK.is_file()
    assert MIGRATION_SELECT_ONLY.is_file()
    assert ROLLBACK_SELECT_ONLY.is_file()
    assert MIGRATION_NULLABLE_UNITS.is_file()
    assert ROLLBACK_NULLABLE_UNITS.is_file()
    up = MIGRATION.read_text(encoding="utf-8")
    down = ROLLBACK.read_text(encoding="utf-8")
    lock = MIGRATION_SELECT_ONLY.read_text(encoding="utf-8")
    for table in REQUIRED_TABLES:
        assert table in up
        assert table in down
    assert "national_coverage_consumer_v1" in up
    assert "CROSS JOIN" in lock
    assert "SELECT-only" in up or "SELECT-only" in lock or "editorial" in up
    assert "extra_1093" in up
    assert "DROP NOT NULL" in MIGRATION_NULLABLE_UNITS.read_text(encoding="utf-8")
    assert "expected_units IS NULL" in ROLLBACK_NULLABLE_UNITS.read_text(encoding="utf-8")


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
    admit_real_db_or_raise(real_db_marker=True)
    payload = evaluate_from_dict(
        json.loads(Path("docs/contracts/national-coverage/fixtures/official-partial.json").read_text(encoding="utf-8"))
    )
    conn = _connect(canonical_dsn())
    conn.autocommit = True
    try:
        _exec_sql(conn, MIGRATION)
        _exec_sql(conn, MIGRATION_SELECT_ONLY)
        _exec_sql(conn, MIGRATION_NULLABLE_UNITS)
        persist_coverage(conn, payload)
        nullable_units = evaluate_from_dict(
            {
                "official": {
                    "status": "AVAILABLE",
                    "source": "pncp",
                    "competence": "contracts-2026",
                    "cutoff": "2026-08-28",
                    "as_of": "2026-08-28T00:00:00Z",
                    "raw_hash": "nullable-unit-denominator",
                    "units_enumerated": False,
                    "orgs": [{"org_id": "11111111000191", "name": "A", "unit_count": 1}],
                },
                "request": {
                    "geography": "BR",
                    "period": "2026",
                    "source": "pncp",
                    "grain": "publishing_org",
                },
            }
        )
        persist_coverage(conn, nullable_units)
        row = select_consumer_answer(
            conn,
            universe_id=payload["national_universe_id"],
            geography=payload["consumer"]["requested_geography"],
            period=payload["consumer"]["requested_period"],
            source=payload["consumer"]["requested_source"],
            grain=payload["consumer"]["requested_grain"],
        )
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT is_insertable_into
                FROM information_schema.views
                WHERE table_schema = 'public' AND table_name = 'national_coverage_consumer_v1'
                """
            )
            insertable = cursor.fetchone()
            cursor.execute("SELECT national_claim_authorized FROM public.national_coverage_consumer_v1 LIMIT 1")
            selected = cursor.fetchone()
            cursor.execute(
                "SELECT expected_units FROM public.national_coverage_universe WHERE universe_id = %s",
                (nullable_units["national_universe_id"],),
            )
            persisted_unknown_units = cursor.fetchone()
            insert_failed = False
            try:
                cursor.execute(
                    """
                    INSERT INTO public.national_coverage_consumer_v1 (
                        requested_geography, requested_period, requested_source, requested_grain,
                        universe_id, expected_partitions, closed_partitions, coverage_pct,
                        national_claim_authorized, verdict, reason_codes, limitations,
                        provenance, content_hash, produced_at
                    ) VALUES (
                        'BR', '2026', 'pncp', 'publishing_org', 'x', 0, 0, 100,
                        true, 'NATIONAL_CLAIM_AUTHORIZED', ARRAY[]::text[], ARRAY[]::text[],
                        '{}'::jsonb, '0'||repeat('a', 63), NOW()
                    )
                    """
                )
            except Exception:
                insert_failed = True
            extra_failed = False
            try:
                cursor.execute(
                    """
                    INSERT INTO public.national_coverage_universe (
                        universe_id, universe_kind, official_source, competence, cutoff,
                        retrieved_at, as_of, raw_hash, catalog_hash, method_version,
                        schema_version, grain, expected_partitions, expected_units,
                        official_status, inclusion_rules, exclusion_rules, owner, next_refresh, payload
                    ) VALUES (
                        'bad-extra', 'OFFICIAL', 'extra_1093', 'c', 'c',
                        'c', 'c', 'r', 'c', 'm',
                        'national-coverage/1.0', 'publishing_org', 0, 0,
                        'AVAILABLE', '[]'::jsonb, '[]'::jsonb, 'o', 'n', '{}'::jsonb
                    )
                    """
                )
            except Exception:
                extra_failed = True
    finally:
        conn.close()
    assert row is not None
    assert row["universe_id"] == payload["national_universe_id"]
    assert row["national_claim_authorized"] is False
    assert row["verdict"] == payload["verdict"]
    assert row["content_hash"] == payload["consumer"]["content_hash"]
    assert insertable is not None
    assert str(insertable[0]).upper() in {"NO", "NEVER", "N"}
    assert selected is not None
    assert selected[0] is False
    assert persisted_unknown_units == (None,)
    assert insert_failed is True
    assert extra_failed is True
