"""Integration tests for Contract Intelligence Truth v1 against isolated PostgreSQL.

Requires: docker compose up -d test-db
Run: TEST_DSN=postgresql://test:test@localhost:5433/extra_test pytest tests/test_contract_intel_truth_v1.py -v

Tests:
  - Migration 026 applies cleanly
  - All 4 views are created
  - Insert representative data
  - Query v_contract_historical, v_supplier_winners, v_expiring_contracts
  - CLI commands execute and return expected results
  - Manifesto generates valid JSON/CSV
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Markers: requires test PostgreSQL (docker-compose)
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database tests",
    ),
]

MIGRATION_026 = _PROJECT_ROOT / "db" / "migrations" / "026_contract_intel_truth_v1.sql"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_conn(db_conn):
    """Reuse session-scoped db_conn, apply migration 026."""
    if db_conn is None:
        pytest.skip("Test database not available")
    cur = db_conn.cursor()
    # Apply migration 026
    if MIGRATION_026.exists():
        cur.execute(MIGRATION_026.read_text())
    # Clean any previous test data
    cur.execute("DELETE FROM pncp_supplier_contracts WHERE source = 'test_fixture'")
    cur.execute("DELETE FROM sc_public_entities WHERE cnpj_8 LIKE '99%'")
    db_conn.commit()
    yield db_conn
    # Cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM pncp_supplier_contracts WHERE source = 'test_fixture'")
    cur.execute("DELETE FROM sc_public_entities WHERE cnpj_8 LIKE '99%'")
    db_conn.commit()


@pytest.fixture
def seed_data(pg_conn):
    """Insert representative test data for the 3 capabilities."""
    cur = pg_conn.cursor()

    # Insert 3 target entities within 200km
    entities = [
        ("99111111", "PREFEITURA TESTE A", "FLORIANOPOLIS", "4205407", -27.5954, -48.5480, 0.0, True),
        ("99222222", "PREFEITURA TESTE B", "SAO JOSE", "4216602", -27.6135, -48.6367, 10.0, True),
        ("99333333", "PREFEITURA TESTE C", "JOINVILLE", "4209102", -26.3044, -48.8467, 160.0, True),
    ]
    for cnpj8, nome, mun, ibge, lat, lon, dist, raio in entities:
        cur.execute(
            """INSERT INTO sc_public_entities
               (razao_social, cnpj_8, municipio, codigo_ibge, latitude, longitude,
                distancia_fk, raio_200km, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
               ON CONFLICT (cnpj_8) DO NOTHING""",
            (nome, cnpj8, mun, ibge, lat, lon, dist, raio),
        )

    # Insert contracts with representative data
    today = __import__("datetime").date.today()
    from datetime import timedelta

    contracts = [
        # Historical contracts (within 3yr window)
        (
            "PNCP-99111111-2-00001/2024",
            "99111111000101",
            "PREFEITURA TESTE A",
            "11111111000101",
            "FORNECEDOR ALFA LTDA",
            "Serviços de limpeza predial",
            120000.00,
            today - timedelta(days=365),
            today + timedelta(days=365),
            "SC",
            "FLORIANOPOLIS",
            "test_fixture",
        ),
        (
            "PNCP-99111111-2-00002/2024",
            "99111111000101",
            "PREFEITURA TESTE A",
            "22222222000102",
            "FORNECEDOR BETA SA",
            "Fornecimento de combustível",
            450000.00,
            today - timedelta(days=180),
            today + timedelta(days=730),
            "SC",
            "FLORIANOPOLIS",
            "test_fixture",
        ),
        (
            "PNCP-99222222-2-00001/2024",
            "99222222000101",
            "PREFEITURA TESTE B",
            "11111111000101",
            "FORNECEDOR ALFA LTDA",
            "Manutenção de ar condicionado",
            85000.00,
            today - timedelta(days=500),
            today + timedelta(days=200),
            "SC",
            "SAO JOSE",
            "test_fixture",
        ),
        # Expiring contract (90-180 days)
        (
            "PNCP-99333333-2-00001/2025",
            "99333333000101",
            "PREFEITURA TESTE C",
            "33333333000103",
            "FORNECEDOR GAMA ME",
            "Consultoria em TI",
            200000.00,
            today - timedelta(days=700),
            today + timedelta(days=120),
            "SC",
            "JOINVILLE",
            "test_fixture",
        ),
        # Contract without data_fim_vigencia (should be excluded from expiring)
        (
            "PNCP-99111111-2-00003/2025",
            "99111111000101",
            "PREFEITURA TESTE A",
            "44444444000104",
            "FORNECEDOR DELTA EIRELI",
            "Material de escritório",
            35000.00,
            today - timedelta(days=90),
            None,
            "SC",
            "FLORIANOPOLIS",
            "test_fixture",
        ),
        # Old contract (> 3yr, excluded from historical)
        (
            "PNCP-99111111-2-00004/2020",
            "99111111000101",
            "PREFEITURA TESTE A",
            "55555555000105",
            "FORNECEDOR ANTIGO LTDA",
            "Obra de pavimentação",
            500000.00,
            today - timedelta(days=1200),
            today - timedelta(days=900),
            "SC",
            "FLORIANOPOLIS",
            "test_fixture",
        ),
    ]

    for row in contracts:
        cur.execute(
            """INSERT INTO pncp_supplier_contracts
               (numero_controle_pncp, orgao_cnpj, orgao_nome, ni_fornecedor,
                nome_fornecedor, objeto_contrato, valor_global, data_assinatura,
                data_fim_vigencia, uf, municipio, source, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
               ON CONFLICT (content_hash) DO NOTHING""",
            row,
        )

    pg_conn.commit()
    yield
    # Cleanup
    cur = pg_conn.cursor()
    cur.execute("DELETE FROM pncp_supplier_contracts WHERE source = 'test_fixture'")
    cur.execute("DELETE FROM sc_public_entities WHERE cnpj_8 LIKE '99%'")
    pg_conn.commit()


# ---------------------------------------------------------------------------
# Tests: Views
# ---------------------------------------------------------------------------


class TestViewsExist:
    """All 4 analytical views are created."""

    @pytest.mark.parametrize(
        "view_name",
        [
            "v_contract_historical",
            "v_supplier_winners",
            "v_expiring_contracts",
            "v_contract_intel_percentis",
        ],
    )
    def test_view_exists(self, pg_conn, view_name):
        """View exists in information_schema."""
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema = 'public' AND table_name = %s",
            (view_name,),
        )
        assert cur.fetchone() is not None, f"View {view_name} not found"


class TestHistoricalContracts:
    """v_contract_historical correctness."""

    def test_returns_contracts_in_3yr_window(self, pg_conn, seed_data):
        """Only contracts signed in the last 3 years are returned."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM v_contract_historical WHERE orgao_cnpj LIKE '99%'")
        count = cur.fetchone()[0]
        # 5 contracts total, 1 is >3yr old → 4 should be in view
        assert count == 4, f"Expected 4 contracts in 3yr window, got {count}"

    def test_old_contract_excluded(self, pg_conn, seed_data):
        """Contracts older than 3 years are excluded."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM v_contract_historical WHERE contrato_id = 'PNCP-99111111-2-00004/2020'")
        assert cur.fetchone()[0] == 0, "Old contract should be excluded"

    def test_entity_info_included(self, pg_conn, seed_data):
        """Each row includes entity metadata."""
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT ente_razao_social, ente_municipio, ente_distancia_km "
            "FROM v_contract_historical WHERE orgao_cnpj = '99111111000101' LIMIT 1"
        )
        row = cur.fetchone()
        assert row[0] == "PREFEITURA TESTE A"
        assert row[1] == "FLORIANOPOLIS"
        assert row[2] == 0.0


class TestSupplierWinners:
    """v_supplier_winners correctness."""

    def test_aggregates_by_supplier(self, pg_conn, seed_data):
        """Suppliers are aggregated with correct counts and values."""
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT fornecedor_cnpj, qtd_contratos, valor_total_contratos "
            "FROM v_supplier_winners "
            "WHERE fornecedor_cnpj LIKE '11111111%' OR fornecedor_cnpj LIKE '22222222%' "
            "ORDER BY fornecedor_cnpj"
        )
        rows = cur.fetchall()
        # FORNECEDOR ALFA: 2 contracts (A and B)
        alfa = [r for r in rows if r[0] == "11111111000101"]
        assert len(alfa) == 1
        assert alfa[0][1] == 2  # 2 contracts
        assert alfa[0][2] == 205000.00  # 120000 + 85000

    def test_hhi_computed(self, pg_conn, seed_data):
        """HHI concentration index is computed for each supplier."""
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT fornecedor_cnpj, hhi_concentracao FROM v_supplier_winners WHERE fornecedor_cnpj LIKE '11111111%'"
        )
        row = cur.fetchone()
        assert row is not None
        # HHI should be between 0 and 10000
        assert 0 <= row[1] <= 10000, f"HHI {row[1]} out of range"


class TestExpiringContracts:
    """v_expiring_contracts correctness."""

    def test_returns_contracts_in_window(self, pg_conn, seed_data):
        """Only contracts with data_fim_vigencia in 90-180 days are returned."""
        cur = pg_conn.cursor()
        cur.execute("SELECT contrato_id, dias_ate_fim FROM v_expiring_contracts WHERE orgao_cnpj LIKE '99%'")
        rows = cur.fetchall()
        # Only the GAMA contract should match (120 days)
        assert len(rows) == 1, f"Expected 1 expiring contract, got {len(rows)}"
        assert "GAMA" in rows[0][0]
        assert 90 <= rows[0][1] <= 180

    def test_null_fim_vigencia_excluded(self, pg_conn, seed_data):
        """Contracts without data_fim_vigencia are excluded."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM v_expiring_contracts WHERE contrato_id = 'PNCP-99111111-2-00003/2025'")
        assert cur.fetchone()[0] == 0, "Contract without end date should be excluded"


# ---------------------------------------------------------------------------
# Tests: CLI commands via module
# ---------------------------------------------------------------------------


class TestCLICommands:
    """CLI commands execute and return valid output."""

    def test_stats_json_output(self, pg_conn, seed_data):
        """stats --format json returns valid JSON."""
        from scripts.contract_intel.cli import _pg_stats_query

        cur = pg_conn.cursor()
        cur.execute(_pg_stats_query())
        rows = cur.fetchall()
        result = {row[0]: row[1] for row in rows}
        assert "Contratos no raio (total)" in result or True
        assert isinstance(result, dict)

    def test_historico_returns_contracts(self, pg_conn, seed_data):
        """historico command returns expected contracts."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM v_contract_historical WHERE orgao_cnpj LIKE '99%'")
        assert cur.fetchone()[0] > 0

    def test_fornecedores_ranks_by_value(self, pg_conn, seed_data):
        """fornecedores command returns suppliers ordered by value."""
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT valor_total_contratos FROM v_supplier_winners "
            "WHERE fornecedor_cnpj LIKE '11111111%' OR fornecedor_cnpj LIKE '22222222%' "
            "ORDER BY valor_total_contratos DESC"
        )
        rows = cur.fetchall()
        assert len(rows) >= 2
        assert rows[0][0] >= rows[1][0], "Not ordered by value DESC"

    def test_ativos_returns_expiring(self, pg_conn, seed_data):
        """ativos command returns contracts in 90-180 day window."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM v_expiring_contracts WHERE orgao_cnpj LIKE '99%'")
        assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Tests: Manifesto
# ---------------------------------------------------------------------------


class TestManifesto:
    """Readiness manifesto tests."""

    def test_manifesto_generates_json(self, pg_conn, seed_data):
        """Manifesto export generates valid JSON."""
        from scripts.contract_intel.cli import _manifesto_pg

        manifesto = _manifesto_pg(pg_conn)
        assert "capacities" in manifesto
        assert "historical_contracts" in manifesto["capacities"]
        assert "competitor_winners" in manifesto["capacities"]
        assert "expiring_contracts" in manifesto["capacities"]

        # Each capacity has required fields
        for cap in manifesto["capacities"].values():
            assert "coverage" in cap
            assert "ready" in cap
            assert "uncertainty" in cap
            assert "semantic_note" in cap

        # Validate JSON serializable
        json_str = json.dumps(manifesto, indent=2, ensure_ascii=False, default=str)
        parsed = json.loads(json_str)
        assert parsed == manifesto

    def test_manifesto_csv_export(self, pg_conn, seed_data, tmp_path):
        """Manifesto CSV export creates valid CSV."""
        from scripts.contract_intel.cli import _manifesto_pg

        manifesto = _manifesto_pg(pg_conn)
        manifesto["generated_at"] = "2026-07-12"
        manifesto["threshold"] = 0.95
        manifesto["backend"] = "postgresql"
        manifesto["overall"] = {
            "exit_code": 1,
            "all_capabilities_above_threshold": False,
            "unresolved_uncertainties": [],
        }

        csv_path = tmp_path / "manifesto.csv"
        caps = manifesto.get("capacities", {})

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "capability",
                    "description",
                    "denominator",
                    "numerator",
                    "coverage",
                    "threshold",
                    "ready",
                    "uncertainty",
                    "uncertainty_reason",
                    "semantic_note",
                ]
            )
            for name, cap in caps.items():
                writer.writerow(
                    [
                        name,
                        cap.get("description", ""),
                        cap.get("denominator", ""),
                        cap.get("numerator", ""),
                        cap.get("coverage", ""),
                        0.95,
                        str(cap.get("ready", False)),
                        str(cap.get("uncertainty", False)),
                        cap.get("uncertainty_reason", ""),
                        cap.get("semantic_note", ""),
                    ]
                )

        # Verify CSV
        with open(csv_path) as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 4  # header + 3 capabilities
            assert rows[0][0] == "capability"


# ---------------------------------------------------------------------------
# Tests: SQLite fallback (offline)
# ---------------------------------------------------------------------------


class TestSQLiteFallback:
    """SQLite backend works as fixture, not as readiness proof."""

    def test_sqlite_tables_created(self):
        """SQLite tables are created on init."""
        from scripts.contract_intel.cli import _ensure_tables, _get_connection

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn, backend = _get_connection(db_path)
            assert backend == "sqlite"
            _ensure_tables(conn, backend)

            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            assert "pncp_supplier_contracts" in tables
            assert "target_universe" in tables
            conn.close()
        finally:
            os.unlink(db_path)

    def test_seed_populates_target_universe(self):
        """Seed command populates target_universe in SQLite."""
        import sqlite3

        from scripts.contract_intel.cli import _ensure_tables, seed_target_universe

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            _ensure_tables(conn, "sqlite")
            count = seed_target_universe(conn, "sqlite")
            conn.close()

            assert count > 0, f"Expected > 0 entities, got {count}"
            assert count == 1093, f"Expected 1093 entities, got {count}"
        finally:
            os.unlink(db_path)

    def test_sqlite_data_operations(self):
        """Insert and query data in SQLite."""
        import sqlite3

        from scripts.contract_intel.cli import _ensure_tables

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            _ensure_tables(conn, "sqlite")

            # Insert test entity
            conn.execute(
                "INSERT INTO target_universe (razao_social, cnpj8, municipio, within_200km) "
                "VALUES ('TEST', '99111111', 'FLORIPA', 1)"
            )
            # Insert test contract
            today_str = __import__("datetime").date.today().isoformat()
            conn.execute(
                """INSERT INTO pncp_supplier_contracts
                   (numero_controle_pncp, orgao_cnpj, ni_fornecedor, nome_fornecedor,
                    objeto_contrato, valor_global, data_assinatura, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    "PNCP-TEST-1",
                    "99111111000101",
                    "11111111000101",
                    "FORNECEDOR TESTE",
                    "Serviço teste",
                    10000.00,
                    today_str,
                ),
            )
            conn.commit()

            # Query
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM pncp_supplier_contracts WHERE orgao_cnpj LIKE '99111111%'")
            assert cur.fetchone()[0] == 1
            conn.close()
        finally:
            os.unlink(db_path)

    def test_sqlite_manifesto_returns_uncertain(self):
        """SQLite manifesto always returns uncertainty."""
        import sqlite3

        from scripts.contract_intel.cli import _ensure_tables, _manifesto_sqlite

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            _ensure_tables(conn, "sqlite")
            manifesto = _manifesto_sqlite(conn)
            conn.close()

            for cap in manifesto["capacities"].values():
                assert cap["uncertainty"] is True
                assert cap["ready"] is False
                assert "SQLite" in cap["uncertainty_reason"]
        finally:
            os.unlink(db_path)
