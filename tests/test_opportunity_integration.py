"""Integration tests for Opportunity Intelligence pipeline.

Requires PostgreSQL with migrations 027-028 applied.
Tests: upsert → query → invariants.

Skip if no DB connection (REQUIRE_OPPORTUNITY_DB=1 to enforce).
"""

from __future__ import annotations

import json
import os

import psycopg2
import psycopg2.extras
import pytest

# Skip unless explicit
pytestmark = pytest.mark.integration

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
)


def _get_conn():
    """Connect to PostgreSQL or skip."""
    try:
        conn = psycopg2.connect(DEFAULT_DSN)
        conn.autocommit = True
        return conn
    except psycopg2.Error as e:
        pytest.skip(f"No database connection: {e}")


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            (table_name,),
        )
        return cur.fetchone()[0]


def _truncate_opportunity_tables(conn):
    """Clean test data from opportunity tables."""
    with conn.cursor() as cur:
        for table in ["opportunity_intel", "opportunity_checkpoints", "opportunity_runs", "opportunity_coverage"]:
            if _table_exists(conn, table):
                cur.execute(f"DELETE FROM {table}")


def _count_table(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}" if _table_exists(conn, table) else "SELECT 0")
        return cur.fetchone()[0]


class TestOpportunityTablesExist:
    """Verify that opportunity tables were created by migrations."""

    def test_opportunity_intel_exists(self):
        conn = _get_conn()
        assert _table_exists(conn, "opportunity_intel")

    def test_opportunity_runs_exists(self):
        conn = _get_conn()
        assert _table_exists(conn, "opportunity_runs")

    def test_opportunity_checkpoints_exists(self):
        conn = _get_conn()
        assert _table_exists(conn, "opportunity_checkpoints")

    def test_opportunity_coverage_exists(self):
        conn = _get_conn()
        assert _table_exists(conn, "opportunity_coverage")


class TestUpsertFunction:
    """Test the upsert_opportunity_intel RPC function."""

    def test_upsert_single_record(self):
        conn = _get_conn()
        _truncate_opportunity_tables(conn)

        batch = [
            {
                "source": "test",
                "source_id": "integration-test-1",
                "source_url": "http://example.com/test1",
                "content_hash": "test-integration-hash-001",
                "orgao_cnpj": "00123456000199",
                "orgao_nome": "Órgão Teste Integração",
                "uf": "SC",
                "municipio": "Florianópolis",
                "objeto": "Teste de integração - upsert",
                "modalidade": "Pregão Eletrônico",
                "valor_estimado": "100000.00",
                "valor_semantica": "estimado",
                "status_canonico": "open",
                "ranking": "GO",
                "ranking_score": "80",
                "ranking_confianca": "HIGH",
            }
        ]

        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM upsert_opportunity_intel(%s::jsonb)",
                (json.dumps(batch),),
            )
            results = cur.fetchall()

        assert len(results) == 1
        action, record_id, content_hash = results[0]
        assert action == "insert"
        assert record_id is not None

        # Query it back
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM opportunity_intel WHERE id = %s", (record_id,))
            row = cur.fetchone()
            assert row is not None
            assert row["source"] == "test"
            assert row["objeto"] == "Teste de integração - upsert"
            assert row["status_canonico"] == "open"
            assert row["uf"] == "SC"

    def test_upsert_idempotent(self):
        """Re-upserting same content_hash should UPDATE, not duplicate."""
        conn = _get_conn()
        _truncate_opportunity_tables(conn)

        batch = [
            {
                "source": "test",
                "source_id": "idempotent-test",
                "content_hash": "idempotent-hash-001",
                "uf": "SC",
                "objeto": "Teste de idempotência v1",
                "status_canonico": "open",
            }
        ]

        with conn.cursor() as cur:
            # First insert
            cur.execute("SELECT * FROM upsert_opportunity_intel(%s::jsonb)", (json.dumps(batch),))
            first = cur.fetchall()
            # Second insert — same hash
            cur.execute("SELECT * FROM upsert_opportunity_intel(%s::jsonb)", (json.dumps(batch),))
            second = cur.fetchall()

        assert first[0][0] == "insert"
        assert second[0][0] == "update"
        # Should still be only 1 row
        count = _count_table(conn, "opportunity_intel")
        assert count == 1

    def test_upsert_batch(self):
        """Test upsert of multiple records."""
        conn = _get_conn()
        _truncate_opportunity_tables(conn)

        batch = []
        for i in range(5):
            batch.append(
                {
                    "source": "test_batch",
                    "source_id": f"batch-{i}",
                    "content_hash": f"batch-hash-{i:03d}",
                    "uf": "SC",
                    "objeto": f"Objeto batch {i}",
                    "status_canonico": "open",
                    "ranking": "REVIEW",
                    "ranking_score": "50",
                }
            )

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM upsert_opportunity_intel(%s::jsonb)", (json.dumps(batch),))
            results = cur.fetchall()

        assert len(results) == 5
        assert all(r[0] == "insert" for r in results)
        assert _count_table(conn, "opportunity_intel") == 5


class TestConstraints:
    """Test database constraints on opportunity_intel."""

    def test_status_canonico_constraint(self):
        """Invalid status_canonico should fail."""
        conn = _get_conn()

        batch = [
            {
                "source": "test",
                "source_id": "bad-status",
                "content_hash": "bad-status-hash-001",
                "uf": "SC",
                "objeto": "Teste status inválido",
                "status_canonico": "INVALID_STATUS_VALUE",
            }
        ]

        with pytest.raises(psycopg2.Error):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM upsert_opportunity_intel(%s::jsonb)",
                    (json.dumps(batch),),
                )

    def test_ranking_constraint(self):
        """Invalid ranking should fail."""
        conn = _get_conn()

        batch = [
            {
                "source": "test",
                "source_id": "bad-ranking",
                "content_hash": "bad-ranking-hash-001",
                "uf": "SC",
                "objeto": "Teste ranking inválido",
                "status_canonico": "open",
                "ranking": "WRONG_TIER",
            }
        ]

        with pytest.raises(psycopg2.Error):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM upsert_opportunity_intel(%s::jsonb)",
                    (json.dumps(batch),),
                )


class TestViews:
    """Test that analytical views work."""

    def v_opportunity_open(self):
        conn = _get_conn()
        if not _table_exists(conn, "opportunity_intel"):
            pytest.skip("opportunity_intel does not exist")

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_opportunity_open LIMIT 1")
            # Should not error even if empty

    def test_v_opportunity_by_source(self):
        conn = _get_conn()
        if not _table_exists(conn, "opportunity_intel"):
            pytest.skip("opportunity_intel does not exist")

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_opportunity_by_source LIMIT 1")

    def test_v_opportunity_coverage_summary(self):
        conn = _get_conn()
        if not _table_exists(conn, "opportunity_intel"):
            pytest.skip("opportunity_intel does not exist")

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_opportunity_coverage_summary LIMIT 1")


class TestInvariants:
    """Test data invariants after upsert."""

    def test_content_hash_unique(self):
        """No two active records should share the same content_hash."""
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT content_hash, COUNT(*) AS cnt
                FROM opportunity_intel
                WHERE is_active = TRUE
                GROUP BY content_hash
                HAVING COUNT(*) > 1
            """)
            duplicates = cur.fetchall()
            assert len(duplicates) == 0, f"Duplicate content_hash found: {duplicates}"

    def test_score_ranges(self):
        """All ranking_scores must be 0-100."""
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM opportunity_intel
                WHERE ranking_score < 0 OR ranking_score > 100
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"Found {bad} records with score out of range"

    def test_status_values(self):
        """All status_canonico must be valid."""
        conn = _get_conn()
        valid = ("open", "upcoming", "closed", "suspended", "revoked", "annulled", "failed", "unknown")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status_canonico, COUNT(*) FROM opportunity_intel
                WHERE status_canonico NOT IN %s
                GROUP BY status_canonico
            """,
                (valid,),
            )
            bad = cur.fetchall()
            assert len(bad) == 0, f"Invalid status_canonico values: {bad}"
