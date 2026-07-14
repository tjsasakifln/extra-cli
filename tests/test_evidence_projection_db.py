"""DB integration tests for Coverage Evidence projection.

Verifies entity-level evidence integrity at the database level.
Uses the local DataLake DB. Safe: negative entity IDs + test run_id prefix.

Run::

    pytest tests/test_evidence_projection_db.py -v --no-cov
"""

from __future__ import annotations

import os

import psycopg2
import pytest

from config.settings import DEFAULT_DSN

pytestmark = [
    pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database tests",
    ),
]


def _conn():
    return psycopg2.connect(DEFAULT_DSN)


def _ensure_test_entities(conn):
    cur = conn.cursor()
    for i in range(-3, 0):
        cur.execute(
            """INSERT INTO sc_public_entities (id, razao_social, cnpj_8, municipio,
               codigo_ibge, is_active, raio_200km)
               VALUES (%s, %s, %s, %s, %s, FALSE, TRUE)
               ON CONFLICT (id) DO NOTHING""",
            (i, f"TEST_ENTITY_{abs(i)}", f"{abs(i):08d}", "Florianopolis", f"{abs(i):07d}"),
        )
    conn.commit()
    cur.close()


def _clean(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM coverage_evidence WHERE run_id LIKE 'test-evid-%'")
    conn.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _setup():
    conn = _conn()
    _ensure_test_entities(conn)
    _clean(conn)
    conn.close()
    yield
    conn = _conn()
    _clean(conn)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════


class TestNullAggregateUniqueness:

    def test_duplicate_null_aggregate_rejected(self):
        conn = _conn()
        cur = conn.cursor()
        run_id = "test-evid-null-unique"

        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, queried_start, queried_end,
                run_id, completed_at, count_obtained, state, metadata)
               VALUES (NULL, 'pncp', 'bids', '2026-07-01', '2026-07-07',
                       %s, NOW(), 500, 'success_with_data', '{}')""",
            (run_id,),
        )
        conn.commit()

        with pytest.raises(Exception) as exc:
            cur.execute(
                """INSERT INTO coverage_evidence
                   (entity_id, source, data_type, queried_start, queried_end,
                    run_id, completed_at, count_obtained, state, metadata)
                   VALUES (NULL, 'pncp', 'bids', '2026-07-01', '2026-07-07',
                           %s, NOW(), 500, 'success_with_data', '{}')""",
                (run_id,),
            )
            conn.commit()

        assert "unique" in str(exc.value).lower() or "duplicate" in str(exc.value).lower()
        conn.rollback()
        cur.close()
        conn.close()

    def test_entity_level_rows_with_different_entity_ids_allowed(self):
        conn = _conn()
        cur = conn.cursor()
        run_id = "test-evid-ent-diff"

        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at, count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', %s, NOW(), 10, 'success_with_data', '{}')""",
            (run_id,),
        )
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at, count_obtained, state, metadata)
               VALUES (-2, 'pncp', 'bids', %s, NOW(), 5, 'success_with_data', '{}')""",
            (run_id,),
        )
        conn.commit()
        # No exception → both inserts succeeded
        cur.execute(
            "SELECT COUNT(*) FROM coverage_evidence WHERE run_id = %s AND entity_id IS NOT NULL",
            (run_id,),
        )
        assert cur.fetchone()[0] == 2
        cur.close()
        conn.close()


class TestEntityEvidenceIdempotency:

    def test_same_run_id_replay_is_noop(self):
        conn = _conn()
        cur = conn.cursor()
        run_id = "test-evid-idem"

        # First write
        cur.execute(
            "DELETE FROM coverage_evidence WHERE entity_id = -1 AND source = 'pncp' AND data_type = 'bids' AND run_id = %s",
            (run_id,),
        )
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at, count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', %s, NOW(), 10, 'success_with_data', '{}')""",
            (run_id,),
        )
        # Second write (same data, same run_id)
        cur.execute(
            "DELETE FROM coverage_evidence WHERE entity_id = -1 AND source = 'pncp' AND data_type = 'bids' AND run_id = %s",
            (run_id,),
        )
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at, count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', %s, NOW(), 10, 'success_with_data', '{}')""",
            (run_id,),
        )
        conn.commit()

        cur.execute(
            "SELECT COUNT(*) FROM coverage_evidence WHERE entity_id = -1 AND source = 'pncp' AND run_id = %s",
            (run_id,),
        )
        assert cur.fetchone()[0] == 1, "Replay duplicated rows"
        cur.close()
        conn.close()


class TestLatestEvidenceView:

    def test_latest_returns_one_row_per_entity(self):
        conn = _conn()
        cur = conn.cursor()

        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at, count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', 'test-evid-v1', '2026-07-01 10:00:00+00', 10, 'success_with_data', '{}')""",
        )
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, queried_start, queried_end,
                run_id, completed_at, count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', '2026-07-01', '2026-07-07',
                       'test-evid-v2', '2026-07-12 10:00:00+00', 20, 'success_zero', '{}')""",
        )
        conn.commit()

        cur.execute(
            """SELECT entity_id, source, state, run_id
               FROM v_latest_evidence
               WHERE entity_id = -1 AND source = 'pncp' AND data_type = 'bids'""",
        )
        rows = cur.fetchall()
        assert len(rows) == 1, f"Expected 1 latest row, got {len(rows)}"
        assert rows[0][2] == "success_zero", f"Expected latest state success_zero, got {rows[0][2]}"
        assert rows[0][3] == "test-evid-v2"
        cur.close()
        conn.close()

    def test_null_entity_in_latest_view(self):
        conn = _conn()
        cur = conn.cursor()
        run_id = "test-evid-agg-view"

        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at, count_obtained, state, metadata)
               VALUES (NULL, 'pncp', 'bids', %s, NOW(), 500, 'success_with_data', '{}')""",
            (run_id,),
        )
        conn.commit()

        cur.execute(
            "SELECT entity_id, source, state FROM v_latest_evidence WHERE entity_id IS NULL AND source = 'pncp'",
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "success_with_data"
        cur.close()
        conn.close()


class TestSuccessZeroCompletenessCheck:

    def test_success_zero_with_queried_dates_accepted(self):
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, queried_start, queried_end,
                run_id, completed_at, count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', '2026-07-01', '2026-07-07',
                       'test-evid-sz-ok', NOW(), 0, 'success_zero', '{}')""",
        )
        conn.commit()  # No CHECK violation
        cur.close()
        conn.close()

    def test_success_zero_with_completeness_metadata_accepted(self):
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, completed_at,
                count_obtained, state, metadata)
               VALUES (-1, 'pncp', 'bids', 'test-evid-sz-meta', NOW(), 0, 'success_zero',
                       '{"completeness": "full_pagination_completed"}')""",
        )
        conn.commit()  # No CHECK violation
        cur.close()
        conn.close()

    def test_success_zero_without_completeness_rejected(self):
        conn = _conn()
        cur = conn.cursor()
        with pytest.raises(Exception) as exc:
            cur.execute(
                """INSERT INTO coverage_evidence
                   (entity_id, source, data_type, run_id, completed_at,
                    count_obtained, state, metadata)
                   VALUES (-1, 'pncp', 'bids', 'test-evid-sz-bad', NOW(), 0,
                           'success_zero', '{}')""",
            )
            conn.commit()

        error_text = str(exc.value).lower()
        assert any(w in error_text for w in ("ck_success_zero", "check", "violation", "violates")), \
            f"Expected CHECK violation, got: {exc.value}"
        conn.rollback()
        cur.close()
        conn.close()


class TestProjectEntityEvidenceIntegration:

    def test_complete_run_writes_one_row_per_entity(self):
        from scripts.crawl.monitor import _project_entity_evidence

        conn = _conn()
        run_id = f"test-evid-project-{os.getpid()}"
        entities = [
            {"id": -1, "razao_social": "TEST_ENTITY_1", "raio_200km": True},
            {"id": -2, "razao_social": "TEST_ENTITY_2", "raio_200km": True},
            {"id": -3, "razao_social": "TEST_ENTITY_3", "raio_200km": True},
        ]

        stats = _project_entity_evidence(
            conn=conn, run_id=run_id, source="pncp", entities=entities,
            fetch_complete=True, date_from="2026-07-01", date_to="2026-07-07",
        )

        assert stats is not None
        assert stats["candidate_entities"] == 3
        assert stats["success_zero"] == 3
        assert stats["success_with_data"] == 0

        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT entity_id) FROM coverage_evidence WHERE run_id = %s AND entity_id IS NOT NULL",
            (run_id,),
        )
        total, distinct = cur.fetchone()
        assert total == 3, f"Expected 3 entity rows, got {total}"
        assert distinct == 3
        cur.close()
        conn.close()

    def test_incomplete_fetch_produces_partial_not_zero(self):
        from scripts.crawl.monitor import _project_entity_evidence

        conn = _conn()
        run_id = f"test-evid-partial-{os.getpid()}"
        entities = [
            {"id": -1, "razao_social": "TEST_ENTITY_1", "raio_200km": True},
        ]

        stats = _project_entity_evidence(
            conn=conn, run_id=run_id, source="pncp", entities=entities,
            fetch_complete=False, date_from="2026-07-01", date_to="2026-07-07",
        )

        assert stats is not None
        assert stats["success_zero"] == 0, "Incomplete fetch must not produce success_zero"
        assert stats["partial"] == 1

        cur = conn.cursor()
        cur.execute(
            "SELECT state FROM coverage_evidence WHERE run_id = %s AND entity_id = -1",
            (run_id,),
        )
        assert cur.fetchone()[0] == "partial"
        cur.close()
        conn.close()

    def test_idempotent_replay_no_duplicates(self):
        from scripts.crawl.monitor import _project_entity_evidence

        conn = _conn()
        run_id = f"test-evid-replay-{os.getpid()}"
        entities = [
            {"id": -1, "razao_social": "TEST_ENTITY_1", "raio_200km": True},
            {"id": -2, "razao_social": "TEST_ENTITY_2", "raio_200km": True},
        ]

        _project_entity_evidence(
            conn=conn, run_id=run_id, source="pncp", entities=entities,
            fetch_complete=True, date_from="2026-07-01", date_to="2026-07-07",
        )
        _project_entity_evidence(
            conn=conn, run_id=run_id, source="pncp", entities=entities,
            fetch_complete=True, date_from="2026-07-01", date_to="2026-07-07",
        )

        cur = conn.cursor()
        cur.execute(
            """SELECT entity_id, COUNT(*) as cnt
               FROM coverage_evidence WHERE run_id = %s AND entity_id IS NOT NULL
               GROUP BY entity_id HAVING COUNT(*) > 1""",
            (run_id,),
        )
        dups = cur.fetchall()
        assert len(dups) == 0, f"Duplicate rows found: {dups}"
        cur.close()
        conn.close()

    def test_source_aggregate_and_entity_rows_coexist(self):
        from scripts.crawl.monitor import _project_entity_evidence
        from scripts.crawl.monitor import _record_evidence

        conn = _conn()
        run_id = f"test-evid-both-{os.getpid()}"
        entities = [
            {"id": -1, "razao_social": "TEST_ENTITY_1", "raio_200km": True},
        ]

        _record_evidence(
            conn, run_id, "pncp", "success",
            fetched=100, transformed=95, persisted=90,
            date_from="2026-07-01", date_to="2026-07-07",
        )
        _project_entity_evidence(
            conn=conn, run_id=run_id, source="pncp", entities=entities,
            fetch_complete=True, date_from="2026-07-01", date_to="2026-07-07",
        )

        cur = conn.cursor()
        cur.execute(
            "SELECT entity_id, state FROM coverage_evidence WHERE run_id = %s ORDER BY entity_id NULLS FIRST",
            (run_id,),
        )
        rows = cur.fetchall()
        assert len(rows) == 2, f"Expected 2 rows (1 aggregate + 1 entity), got {len(rows)}"
        assert rows[0][0] is None, "First row should be source-level aggregate (NULL entity)"
        assert rows[1][0] == -1, "Second row should be entity-level"
        cur.close()
        conn.close()
