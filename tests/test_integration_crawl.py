"""Integration tests for crawl pipeline with real PostgreSQL.

Requires:
    A running PostgreSQL with the test schema applied.
    Set TEST_DSN env var or use default.

    pytest -m integration -v
    REQUIRE_TEST_DB=1 pytest -m "integration or database" -v

Markers:
    integration — requires PostgreSQL
    database — modifies PostgreSQL
"""

from __future__ import annotations

import json
import os

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_db():
    """Skip or fail based on REQUIRE_TEST_DB env var."""
    dsn = os.getenv("TEST_DSN", "postgresql://postgres@localhost:5433/postgres")
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
    dsn = os.getenv("TEST_DSN", "postgresql://postgres@localhost:5433/postgres")
    return psycopg2.connect(dsn)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database integration tests",
    ),
]


class TestDatabaseConnectivity:
    """Verify PostgreSQL is reachable."""

    def test_can_connect(self):
        _require_db()
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
        cur.close()
        conn.close()


class TestSchemaExists:
    """Verify core tables exist."""

    def test_pncp_raw_bids_table(self):
        _require_db()
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'pncp_raw_bids'
            )
        """)
        assert cur.fetchone()[0], "pncp_raw_bids table missing"
        cur.close()
        conn.close()

    def test_entity_coverage_table(self):
        _require_db()
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'entity_coverage'
            )
        """)
        assert cur.fetchone()[0], "entity_coverage table missing"
        cur.close()
        conn.close()

    def test_ingestion_runs_table(self):
        _require_db()
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'ingestion_runs'
            )
        """)
        assert cur.fetchone()[0], "ingestion_runs table missing"
        cur.close()
        conn.close()


class TestUpsertRPC:
    """Verify upsert_pncp_raw_bids RPC works with real data."""

    def test_upsert_minimal_record(self):
        """Insert and retrieve a minimal valid record."""
        _require_db()
        conn = _get_conn()
        cur = conn.cursor()

        test_id = "test_integration_001"
        record = [{
            "pncp_id": test_id,
            "objeto_compra": "Objeto de teste integracao",
            "valor_total_estimado": 50000.00,
            "modalidade_id": 5,
            "modalidade_nome": "Pregao Eletronico",
            "esfera_id": 3,
            "uf": "SC",
            "municipio": "Florianopolis",
            "codigo_municipio_ibge": "4205407",
            "orgao_razao_social": "Prefeitura Municipal de Florianopolis",
            "orgao_cnpj": "82892598000199",
            "data_publicacao": "2026-07-01",
            "data_abertura": None,
            "data_encerramento": None,
            "link_pncp": "https://pncp.gov.br/test/001",
            "content_hash": "test_integration_hash_001",
            "source": "test_integration",
            "source_id": "test_integration_src_001",
        }]

        try:
            cur.execute("SELECT * FROM upsert_pncp_raw_bids(%s)", (json.dumps(record),))
            rows = cur.fetchall()
            conn.commit()

            assert len(rows) >= 1, "RPC returned no rows"
            action = rows[0][0]
            assert action in ("inserted", "skipped"), f"Unexpected action: {action}"

            # Read back
            cur.execute(
                "SELECT pncp_id, objeto_compra, valor_total_estimado FROM pncp_raw_bids WHERE pncp_id = %s",
                (test_id,),
            )
            row = cur.fetchone()
            assert row is not None, "Record not found after upsert"
            assert row[0] == test_id
            assert "integracao" in row[1]
            assert float(row[2]) == 50000.00

        finally:
            # Cleanup
            cur.execute("DELETE FROM pncp_raw_bids WHERE source = 'test_integration'")
            conn.commit()
            cur.close()
            conn.close()

    def test_upsert_content_hash_dedup(self):
        """Same content_hash should be skipped on second upsert."""
        _require_db()
        conn = _get_conn()
        cur = conn.cursor()

        record = [{
            "pncp_id": "test_dedup_002",
            "objeto_compra": "Teste dedup",
            "valor_total_estimado": 100.00,
            "modalidade_id": 5,
            "modalidade_nome": "Pregao",
            "esfera_id": 3,
            "uf": "SC",
            "municipio": "Test",
            "codigo_municipio_ibge": "4205407",
            "orgao_razao_social": "Test",
            "orgao_cnpj": "12345678000199",
            "data_publicacao": "2026-07-01",
            "link_pncp": "https://test.com",
            "content_hash": "test_dedup_hash_unique",
            "source": "test_integration",
            "source_id": "test_dedup_src",
        }]

        try:
            # First insert
            cur.execute("SELECT * FROM upsert_pncp_raw_bids(%s)", (json.dumps(record),))
            rows1 = cur.fetchall()
            conn.commit()
            assert rows1[0][0] == "inserted"

            # Second insert with same content_hash
            cur.execute("SELECT * FROM upsert_pncp_raw_bids(%s)", (json.dumps(record),))
            rows2 = cur.fetchall()
            conn.commit()
            assert rows2[0][0] == "skipped", f"Expected 'skipped', got '{rows2[0][0]}'"

        finally:
            cur.execute("DELETE FROM pncp_raw_bids WHERE source = 'test_integration'")
            conn.commit()
            cur.close()
            conn.close()


class TestSeleniumSchemaContract:
    """Verify Selenium transform output is accepted by upsert_pncp_raw_bids."""

    def test_selenium_record_accepted_by_rpc(self):
        """Transform a Selenium record and upsert it via RPC."""
        _require_db()
        from scripts.crawl.selenium_crawler_adapter import transform

        # Simulate a Selenium crawl result
        sample = [{
            "status": "ok",
            "slug": "florianopolis",
            "municipio": "Florianopolis",
            "ibge": "4205407",
            "url": "https://example.com/portal",
            "bids": [{
                "orgao_nome": "Prefeitura de Florianopolis",
                "orgao_cnpj": "82892598000199",
                "modalidade": "Pregao",
                "objeto": "Contratacao de servicos de TI",
                "data_publicacao": "2026-07-11",
                "valor": "R$ 150.000,00",
                "portal_url": "https://example.com/lic/1",
            }],
        }]

        records = transform(sample)
        assert len(records) == 1

        conn = _get_conn()
        cur = conn.cursor()

        try:
            cur.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s)",
                (json.dumps(records),),
            )
            rows = cur.fetchall()
            conn.commit()
            assert len(rows) == 1
            action = rows[0][0]
            assert action in ("inserted", "skipped"), f"Selenium record rejected: {action}"

            if action == "inserted":
                # Read back
                cur.execute(
                    "SELECT pncp_id, objeto_compra, valor_total_estimado, modalidade_nome, source_id "
                    "FROM pncp_raw_bids WHERE source_id LIKE 'selenium_florianopolis%'"
                )
                row = cur.fetchone()
                assert row is not None, "Selenium record not persisted"
                assert row[0].startswith("sel_"), f"pncp_id: {row[0]}"
                assert "TI" in row[1], f"objeto_compra: {row[1]}"
                assert float(row[2]) == 150000.00
                assert row[3] == "Pregao Eletronico"

        finally:
            cur.execute("DELETE FROM pncp_raw_bids WHERE source_id LIKE 'selenium_%'")
            conn.commit()
            cur.close()
            conn.close()


class TestSourceRegistry:
    """Verify all registered modules are importable and have required API."""

    def test_all_modules_importable(self):
        """Every source in the registry must be importable."""
        import importlib
        from scripts.crawl.registry import iter_sources

        for info in iter_sources():
            mod = importlib.import_module(f"scripts.crawl.{info.module}")
            assert hasattr(mod, "crawl"), f"{info.name}: missing crawl()"
            assert hasattr(mod, "transform"), f"{info.name}: missing transform()"
            assert callable(mod.crawl)
            assert callable(mod.transform)

    def test_no_duplicate_names(self):
        """Registry must not contain duplicate source names."""
        from scripts.crawl.registry import iter_sources
        names = [s.name for s in iter_sources()]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"


class TestCrawlerResultStatus:
    """Verify determine_status() logic."""

    def test_status_rules(self):
        from scripts.crawl.ingestion._base.crawler import determine_status

        assert determine_status(fetched=10, transformed=5) == "success"
        assert determine_status(fetched=10, transformed=0) == "degraded"
        # coverage_only WITHOUT evidence → degraded (not success)
        assert determine_status(fetched=10, transformed=0, purpose="coverage_only") == "degraded"
        # coverage_only WITH evidence → success
        assert determine_status(fetched=10, transformed=0, purpose="coverage_only", entities_covered=5) == "success"
        assert determine_status(fetched=0, transformed=0) == "empty"
        assert determine_status(fetched=10, transformed=5, errors=["fail"]) == "failed"
        assert determine_status(fetched=10, transformed=5, warnings=["warn"]) == "degraded"


class TestDateForwarding:
    """Verify --date-from/--date-to args reach crawl_source."""

    def test_date_args_accepted_by_crawl_source(self):
        """crawl_source() must accept date_from/date_to kwargs."""
        import inspect
        from scripts.crawl.monitor import crawl_source

        sig = inspect.signature(crawl_source)
        params = list(sig.parameters.keys())
        assert "date_from" in params, f"crawl_source missing date_from param: {params}"
        assert "date_to" in params, f"crawl_source missing date_to param: {params}"


class TestRegistryEquality:
    """Verify registry sources match across all consumers."""

    def test_registry_matches_monitor_sources(self):
        from scripts.crawl.registry import iter_sources
        from scripts.crawl.monitor import SOURCES

        registry_names = {s.name for s in iter_sources()}
        monitor_names = set(SOURCES)
        assert registry_names == monitor_names, (
            f"Registry-monitor mismatch. "
            f"Only in registry: {registry_names - monitor_names}. "
            f"Only in monitor: {monitor_names - registry_names}"
        )

    def test_registry_matches_backfill_sources(self):
        from scripts.crawl.registry import iter_sources
        from scripts.pipeline.backfill_multi_source import SOURCE_ORDER

        registry_names = {s.name for s in iter_sources() if s.name != "transparencia_residual"}
        backfill_names = set(SOURCE_ORDER)
        assert registry_names == backfill_names, (
            f"Registry-backfill mismatch. "
            f"Only in registry: {registry_names - backfill_names}. "
            f"Only in backfill: {backfill_names - registry_names}"
        )

    def test_registry_matches_smoke_test_sources(self):
        from scripts.crawl.registry import iter_sources
        from tests.smoke.test_smoke_sources import CRAWLER_MODULES, _init_from_registry

        _init_from_registry()
        registry_names = {s.name for s in iter_sources()}
        smoke_names = set(CRAWLER_MODULES.keys())
        assert registry_names == smoke_names, (
            f"Registry-smoke mismatch. "
            f"Only in registry: {registry_names - smoke_names}. "
            f"Only in smoke: {smoke_names - registry_names}"
        )

    def test_transparencia_residual_not_in_registry(self):
        """transparencia_residual must NOT be in the active registry."""
        from scripts.crawl.registry import lookup
        assert lookup("transparencia_residual") is None


class TestAllMigrationsApplied:
    """Verify all migrations apply cleanly to a fresh database.

    Requires REQUIRE_TEST_DB=1 to fail hard on migration errors.
    Without it, tests are skipped if the DB is unavailable.
    """

    def test_all_migrations_applied_on_clean_db(self):
        """Every migration in db/migrations/ must be applicable without error.

        This test verifies:
        1. All migrations are present
        2. No migration fails when applied to a clean database
        3. Migration files are listed
        """
        _require_db()

        from pathlib import Path
        MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"

        assert MIGRATIONS_DIR.exists(), (
            f"Migrations directory not found: {MIGRATIONS_DIR}"
        )

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        assert len(migration_files) > 0, "No migration files found"

        conn = _get_conn()
        failures: list[tuple[str, str]] = []
        applied: list[str] = []

        try:
            conn.autocommit = True
            for sql_file in migration_files:
                try:
                    with open(sql_file) as f:
                        conn.cursor().execute(f.read())
                    applied.append(sql_file.name)
                except Exception as e:
                    error_msg = str(e)[:200]
                    failures.append((sql_file.name, error_msg))

            print(f"\n  Migrations applied: {len(applied)}")
            for name in applied:
                print(f"    ✓ {name}")

            if failures:
                print(f"\n  Migrations failed: {len(failures)}")
                for name, error in failures:
                    print(f"    ✗ {name}: {error}")
                pytest.fail(
                    f"{len(failures)} migration(s) failed on clean database:\n"
                    + "\n".join(f"  - {n}: {e}" for n, e in failures)
                )
            else:
                print(f"\n  All {len(applied)} migrations applied successfully.")

        finally:
            conn.close()

    def test_migration_files_exist(self):
        """Migration directory must contain SQL files."""
        from pathlib import Path
        MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"

        if not MIGRATIONS_DIR.exists():
            pytest.fail(f"Migrations directory missing: {MIGRATIONS_DIR}")

        sql_files = list(MIGRATIONS_DIR.glob("*.sql"))
        assert len(sql_files) > 0, (
            f"No .sql files found in {MIGRATIONS_DIR}"
        )
        print(f"  Found {len(sql_files)} migration files:")
        for f in sorted(sql_files):
            print(f"    {f.name}")
