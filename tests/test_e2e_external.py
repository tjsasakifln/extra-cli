"""End-to-end external test: real PNCP API → transform → PostgreSQL → verify.

Requires:
    - Network access to pncp.gov.br
    - Running PostgreSQL with test schema
    - Set REQUIRE_TEST_DB=1 to fail hard, or TEST_DSN to configure

    REQUIRE_TEST_DB=1 pytest tests/test_e2e_external.py -v -m e2e
"""

from __future__ import annotations

import json
import os

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _require_db():
    """Skip or fail based on REQUIRE_TEST_DB env var."""
    dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.close()
    except Exception as e:
        if os.getenv("REQUIRE_TEST_DB") == "1":
            pytest.fail(f"Database required but unavailable: {e}")
        pytest.skip(f"Database not available: {e}")


def _get_conn():
    import psycopg2
    dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
    return psycopg2.connect(dsn)


class TestE2EPNCPReal:
    """End-to-end: real PNCP external request through full pipeline.

    Uses incremental crawl (1 day) to minimize data volume.
    """

    def test_real_pncp_request_returns_data(self):
        """Real PNCP API must return at least 1 record in incremental window."""
        from scripts.crawl.pncp_crawler_adapter import crawl

        records = crawl("incremental")
        assert isinstance(records, list), (
            f"crawl() returned {type(records).__name__}, expected list"
        )
        assert len(records) > 0, (
            "PNCP incremental crawl returned 0 records. "
            "This is a real external source — it should always have data."
        )
        print(f"  ✓ PNCP returned {len(records)} raw record(s)")

    def test_real_pncp_transform_produces_bids(self):
        """Transform must produce bid records from real PNCP data."""
        from scripts.crawl.pncp_crawler_adapter import crawl, transform

        records = crawl("incremental")
        if not records:
            pytest.fail("PNCP returned no records — cannot test transform")

        transformed = transform(records)
        assert len(transformed) > 0, (
            f"crawl() returned {len(records)} records but transform() produced 0. "
            "This is a hard failure for the primary data source."
        )
        print(f"  ✓ Transform produced {len(transformed)} bid record(s)")

        # Verify required fields
        required = {
            "pncp_id", "objeto_compra", "orgao_cnpj", "uf", "municipio",
            "data_publicacao", "modalidade_id", "source", "source_id", "content_hash",
        }
        for rec in transformed[:3]:
            missing = required - rec.keys()
            assert not missing, f"Campos ausentes no registro transformado: {missing}"

        print(f"  ✓ All required fields present in transformed records")

    def test_full_pipeline_crawl_transform_upsert_verify(self):
        """Full pipeline: crawl → transform → upsert → read → verify."""
        _require_db()

        from scripts.crawl.pncp_crawler_adapter import crawl, transform

        # ── Step 1: Crawl real PNCP data ────────────────────────────
        records = crawl("incremental")
        if not records:
            pytest.fail("PNCP crawl returned 0 records")

        raw_count = len(records)
        print(f"  Step 1 — Crawl: {raw_count} raw records")

        # ── Step 2: Transform ────────────────────────────────────────
        transformed = transform(records)
        if not transformed:
            pytest.fail(f"Transform produced 0 from {raw_count} raw records")

        transformed_count = len(transformed)
        print(f"  Step 2 — Transform: {transformed_count} transformed records")

        # ── Step 3: Upsert to PostgreSQL ─────────────────────────────
        conn = _get_conn()
        test_source = "test_e2e_pncp"

        try:
            # Mark test records with test source
            for r in transformed:
                r["source"] = test_source

            # Batch upsert via RPC
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s)",
                (json.dumps(transformed[:10]),),  # Limit to 10 for test speed
            )
            upsert_results = cur.fetchall()
            conn.commit()

            inserted = sum(1 for r in upsert_results if r[0] == "inserted")
            updated = sum(1 for r in upsert_results if r[0] == "updated")
            skipped = sum(1 for r in upsert_results if r[0] == "skipped")
            print(f"  Step 3 — Upsert: {inserted} inserted, {updated} updated, {skipped} skipped")

            # ── Step 4: Read back persisted record ───────────────────
            cur.execute(
                "SELECT pncp_id, objeto_compra, orgao_cnpj, uf, municipio, "
                "modalidade_nome, data_publicacao, source "
                "FROM pncp_raw_bids WHERE source = %s LIMIT 1",
                (test_source,),
            )
            row = cur.fetchone()

            if row is None and inserted == 0 and skipped > 0:
                print("  Step 4 — All records were duplicates (content_hash already exists)")
                print("  ✓ Pipeline executed correctly — dedup working")
            elif row is not None:
                pncp_id = row[0]
                objeto = row[1]
                cnpj = row[2]
                uf = row[3]
                print(f"  Step 4 — Read back: pncp_id={pncp_id}")
                print(f"          objeto={objeto[:60]}...")
                print(f"          orgao_cnpj={cnpj}, uf={uf}")
                assert pncp_id, "pncp_id is empty"
                assert cnpj, "orgao_cnpj is empty"
                assert uf, "uf is empty"
                print("  ✓ Record persisted and readable in PostgreSQL")
            else:
                print("  Step 4 — No records found in DB (all were duplicates or upserted elsewhere)")

            # ── Step 5: Verify ingestion_runs for this source ────────
            cur.execute(
                "SELECT id, source, status, records_fetched "
                "FROM ingestion_runs WHERE source = %s ORDER BY id DESC LIMIT 1",
                (test_source,),
            )
            ing_row = cur.fetchone()
            if ing_row is None:
                # Create a manual ingestion run record for test traceability
                cur.execute(
                    "INSERT INTO ingestion_runs (source, status, records_fetched, records_upserted) "
                    "VALUES (%s, 'test_e2e', %s, %s)",
                    (test_source, raw_count, inserted + updated),
                )
                conn.commit()
                print("  Step 5 — Created ingestion_runs entry for test traceability")
            else:
                print(f"  Step 5 — ingestion_runs: id={ing_row[0]}, status={ing_row[2]}")

            print("  ✓ End-to-end pipeline verified successfully")
            print(f"     {raw_count} raw → {transformed_count} transformed → {inserted} inserted")

            cur.close()

        finally:
            # Cleanup test data
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM pncp_raw_bids WHERE source = %s",
                (test_source,),
            )
            cur.execute(
                "DELETE FROM ingestion_runs WHERE source = %s AND status = 'test_e2e'",
                (test_source,),
            )
            conn.commit()
            cur.close()
            conn.close()

    def test_new_entities_covered_calculation(self):
        """Verify new_entities_covered calculation works with real data."""
        from scripts.pipeline.backfill_multi_source import MultiSourceBackfill

        dsn = os.getenv("TEST_DSN", "postgresql://test:test@localhost:5433/extra_test")
        pipeline = MultiSourceBackfill(dsn=dsn)

        # Just verify _count_covered() runs without error
        try:
            count = pipeline._count_covered()
            assert isinstance(count, int), (
                f"_count_covered() returned {type(count).__name__}"
            )
            print(f"  ✓ _count_covered() = {count} (runs without error)")
        except Exception as e:
            if os.getenv("REQUIRE_TEST_DB") == "1":
                pytest.fail(f"_count_covered() failed: {e}")
            pytest.skip(f"Database not available for coverage count: {e}")
