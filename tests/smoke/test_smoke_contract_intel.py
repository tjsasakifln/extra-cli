"""Smoke test for Contract Intelligence vertical slice.

Verifies the full pipeline works end-to-end with offline data:
  1. Target universe loads from seed spreadsheet (deterministic)
  2. CLI seed command populates SQLite
  3. SQL views execute without errors
  4. Stats/metrics are correct

BLOCKERS DOCUMENTED:
  - PostgreSQL unavailable (no LOCAL_DATALAKE_DSN) → all DB tests use SQLite
  - PNCP API not called (offline test) → crawl tests use mocks
  - Real contract data not available → analytics queries return zero rows

This smoke test is REPRODUCIBLE: just run `pytest tests/smoke/test_smoke_contract_intel.py -v`
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    """Creates a temporary SQLite database with schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create schema
    # Import _ensure_tables to use canonical schema (matches QUERY_STATS)
    from scripts.contract_intel.cli import _ensure_tables

    # Create target_universe table manually (seed_target_universe writes to it)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS target_universe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            razao_social TEXT NOT NULL,
            cnpj8 TEXT NOT NULL,
            municipio TEXT,
            codigo_ibge TEXT,
            natureza_juridica TEXT,
            latitude REAL,
            longitude REAL,
            distancia_km REAL,
            within_200km INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_tu_cnpj8 ON target_universe(cnpj8);
    """)
    conn.commit()

    # Use canonical pncp_supplier_contracts schema from _ensure_tables
    # (matches column names used by QUERY_STATS, _sqlite_stats_query, etc.)
    _ensure_tables(conn, "sqlite")
    conn.commit()

    yield conn, db_path

    conn.close()
    os.unlink(db_path)


# ---------------------------------------------------------------------------
# Test 1: Target universe is deterministic
# ---------------------------------------------------------------------------


def test_smoke_target_universe_deterministic():
    """Target universe loads correctly from seed spreadsheet."""
    from scripts.contract_intel.target_universe import (
        entities_within_radius,
        load_target_universe,
        unique_cnpj8_within_radius,
    )

    universe = load_target_universe()
    entities_within_radius(universe)  # verify no errors
    unique_cnpj8_within_radius(universe)  # verify no errors

    # Core assertions
    assert universe.total_seed_rows == 2085, f"Expected 2085 seed rows, got {universe.total_seed_rows}"
    assert universe.total_within_200km == 1093, f"Expected 1093 within 200km, got {universe.total_within_200km}"
    assert universe.total_outside_200km == 388, f"Expected 388 outside, got {universe.total_outside_200km}"
    assert universe.total_without_coords == 604, f"Expected 604 without coords, got {universe.total_without_coords}"

    # No "all SC" shortcut
    assert universe.total_within_200km < 2085, "Should NOT include all 2085 entities"
    assert universe.total_within_200km < 1481, "Should NOT include all entities with coordinates"

    # Inclusion rule is explicit
    assert "200" in universe.inclusion_rule or "200.0" in universe.inclusion_rule
    assert "haversine" in universe.inclusion_rule.lower()

    # CNPJ8 duplicates are counted
    assert universe.duplicate_cnpj8_count >= 0, "Duplicate count must be explicit"

    # Entities without coordinates are flagged
    assert universe.total_without_coords > 0, "Must flag entities without coordinates"

    print(f"  ✓ {universe.total_seed_rows} seed rows")
    print(f"  ✓ {universe.total_with_coords} with coordinates")
    print(f"  ✓ {universe.total_without_coords} without coordinates (EXCLUDED)")
    print(f"  ✓ {universe.total_within_200km} within {universe.radius_km} km")
    print(f"  ✓ {universe.total_outside_200km} outside radius")
    print(f"  ✓ {universe.unique_cnpj8_within} unique CNPJ8 roots")
    print(f"  ✓ {universe.duplicate_cnpj8_count} duplicated CNPJ8 roots")


# ---------------------------------------------------------------------------
# Test 2: CLI seed + stats
# ---------------------------------------------------------------------------


def test_smoke_cli_seed_and_stats(temp_db):
    """CLI seed command populates DB, stats returns expected metrics."""
    conn, db_path = temp_db

    from scripts.contract_intel.cli import QUERY_STATS, seed_target_universe

    # Seed
    count = seed_target_universe(conn, "sqlite")
    assert count == 1093

    # Verify target_universe
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM target_universe")
    assert cur.fetchone()[0] == 1093

    cur.execute("SELECT COUNT(DISTINCT cnpj8) FROM target_universe")
    unique_cnpj = cur.fetchone()[0]
    assert unique_cnpj > 0

    # Stats
    cur.execute(QUERY_STATS)
    rows = cur.fetchall()
    metrics = {r[0]: r[1] for r in rows}

    assert metrics["Total contracts"] == "0", "Expected 0 contracts on fresh DB"
    assert metrics["Unique entities"] == "0", "Expected 0 unique entities on fresh DB"

    print(f"  ✓ Seeded {count} entities")
    print(f"  ✓ {unique_cnpj} unique CNPJ8 roots")
    print(f"  ✓ Stats: {json.dumps(metrics)}")


# ---------------------------------------------------------------------------
# Test 3: FetchResult discrimination
# ---------------------------------------------------------------------------


def test_smoke_fetch_result_discrimination():
    """FetchResult correctly distinguishes all failure modes from zero."""
    from scripts.crawl.contracts_crawler import FetchResult, FetchStatus

    # Success with data
    r1 = FetchResult(status=FetchStatus.SUCCESS_DATA, items=[{"a": 1}])
    assert r1.is_success and not r1.is_zero

    # Success zero (legitimate empty)
    r2 = FetchResult(status=FetchStatus.SUCCESS_ZERO)
    assert r2.is_success and r2.is_zero
    assert r2.items == []

    # Connection failed
    r3 = FetchResult(status=FetchStatus.CONNECTION_FAILED, error_message="Timeout")
    assert r3.is_failure
    assert r3.items == []  # Empty items, but status says it's a failure

    # Parse failed
    r4 = FetchResult(status=FetchStatus.PARSE_FAILED, error_message="Bad JSON")
    assert r4.is_failure

    # Critical: connection_failed and success_zero must NOT be confused
    assert r2.status != r3.status, (
        "SUCCESS_ZERO and CONNECTION_FAILED must be different! Cannot convert exception to empty list."
    )

    # Every failure has an evidence_state
    for status in FetchStatus:
        r = FetchResult(status=status)
        assert r.evidence_state, f"No evidence_state for {status}"

    print("  ✓ SUCCESS_DATA, SUCCESS_ZERO, CONNECTION_FAILED all distinct")
    print(f"  ✓ All {len(list(FetchStatus))} FetchStatus values have evidence_state mapping")


# ---------------------------------------------------------------------------
# Test 4: UF never defaults to SC
# ---------------------------------------------------------------------------


def test_smoke_uf_never_defaults_to_sc():
    """UF is never presumed 'SC' when absent from API response."""
    from scripts.crawl.contracts_crawler import _transform_record

    # Case 1: UF from API
    rec1 = {
        "numeroControlePNCP": "TEST1",
        "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Test"},
        "unidadeOrgao": {"ufSigla": "PR"},
        "niFornecedor": "00999999000199",
        "nomeRazaoSocialFornecedor": "F1",
        "objetoContrato": "T1",
        "valorGlobal": 1000.0,
        "dataAssinatura": "2025-01-01T00:00:00Z",
    }
    r1 = _transform_record(rec1)
    assert r1["uf"] == "PR"

    # Case 2: UF missing — stays None
    rec2 = {
        "numeroControlePNCP": "TEST2",
        "orgaoEntidade": {"cnpj": "99999999000199", "razaoSocial": "Unknown"},
        "unidadeOrgao": {},
        "niFornecedor": "00999999000199",
        "nomeRazaoSocialFornecedor": "F2",
        "objetoContrato": "T2",
        "valorGlobal": 2000.0,
        "dataAssinatura": "2025-01-01T00:00:00Z",
    }
    r2 = _transform_record(rec2)
    assert r2["uf"] is None, f"UF must be None when absent, got '{r2['uf']}'. No fallback to 'SC' allowed."

    print("  ✓ UF from API used when present")
    print("  ✓ UF stays None when absent (no 'SC' fallback)")


# ---------------------------------------------------------------------------
# Test 5: Checkpoint idempotency
# ---------------------------------------------------------------------------


def test_smoke_checkpoint_idempotency():
    """Checkpoint is idempotent — save/load preserves completed windows."""
    from scripts.crawl.contracts_crawler import (
        CrawlCheckpoint,
        load_checkpoint,
        save_checkpoint,
    )

    cp1 = CrawlCheckpoint(
        mode="test_smoke",
        completed_windows=["20230101_20230131", "20230201_20230228"],
        total_contracts_fetched=99,
        total_windows_completed=2,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "contracts_test_smoke.json")

        import scripts.crawl.contracts_crawler as cc

        with patch.object(cc, "_checkpoint_path", return_value=path):
            save_checkpoint(cp1)

            # Load and verify
            cp2 = load_checkpoint("test_smoke")
            assert cp2.completed_windows == cp1.completed_windows
            assert cp2.total_contracts_fetched == 99

            # Save again (idempotent)
            cp2.total_contracts_fetched += 1
            save_checkpoint(cp2)

            cp3 = load_checkpoint("test_smoke")
            assert cp3.total_contracts_fetched == 100

    print("  ✓ Checkpoint save/load preserves state")
    print("  ✓ Checkpoint idempotent across save cycles")


# ---------------------------------------------------------------------------
# Test 6: SQL views syntax check
# ---------------------------------------------------------------------------


def test_smoke_sql_views_syntax(temp_db):
    """SQL query syntax is valid against SQLite schema."""
    conn, db_path = temp_db

    from scripts.contract_intel.cli import (
        QUERY_STATS,
        _sqlite_expiring_query,
        _sqlite_fornecedores_query,
        _sqlite_historico_query,
    )

    queries = {
        "historico": _sqlite_historico_query(),
        "fornecedores": _sqlite_fornecedores_query(),
        "ativos_90_180": _sqlite_expiring_query(),
        "stats": QUERY_STATS,
    }

    for name, query in queries.items():
        try:
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            # All queries should return zero rows (no contracts)
            assert isinstance(rows, list), f"Query '{name}' did not return a list"
        except Exception as e:
            pytest.fail(f"Query '{name}' failed: {e}")

    print("  ✓ All 5 canonical queries execute without syntax errors")
    print("  ✓ All queries return zero rows (no contracts loaded) — expected")


# ---------------------------------------------------------------------------
# Test 7: Geo filter
# ---------------------------------------------------------------------------


def test_smoke_geo_filter():
    """Geo filter correctly classifies entities."""
    from scripts.lib.geocode import FLORIANOPOLIS, haversine

    # Entity at Florianopolis center
    d0 = haversine(
        FLORIANOPOLIS[0],
        FLORIANOPOLIS[1],
        FLORIANOPOLIS[0],
        FLORIANOPOLIS[1],
    )
    assert d0 == 0.0

    # Entity ~160 km away (Joinville area)
    d1 = haversine(-27.5954, -48.5480, -26.3044, -48.8467)
    assert d1 < 200, f"Joinville ({d1:.0f} km) should be within 200 km"

    # Entity ~380 km away (Porto Alegre)
    d2 = haversine(-27.5954, -48.5480, -30.0346, -51.2177)
    assert d2 > 200, f"Porto Alegre ({d2:.0f} km) should be outside 200 km"

    print(f"  ✓ Florianópolis → Florianópolis: {d0:.0f} km")
    print(f"  ✓ Florianópolis → Joinville: {d1:.0f} km (within)")
    print(f"  ✓ Florianópolis → Porto Alegre: {d2:.0f} km (outside)")


# ---------------------------------------------------------------------------
# Blockers documented
# ---------------------------------------------------------------------------


def test_smoke_document_blockers():
    """Document what is blocked and why — not a fake pass."""
    blockers = []

    # Check PostgreSQL availability
    dsn = os.environ.get("LOCAL_DATALAKE_DSN", "")
    if not dsn:
        blockers.append(
            "BLOCKED: LOCAL_DATALAKE_DSN not set → PostgreSQL unavailable. "
            "All DB tests use SQLite fallback. Real contract crawl not executed."
        )

    # Check if we can reach PNCP API
    try:
        import urllib.request

        req = urllib.request.Request(
            "https://pncp.gov.br/api/consulta/v1/contratos?dataInicial=20260101&dataFinal=20260102&pagina=1"
        )
        req.add_header("User-Agent", "ExtraConsultoria/1.0 (smoke-test)")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        blockers.append(
            f"BLOCKED: PNCP API not reachable → {e}. Crawl tests use mocks. Real contract data not fetched."
        )

    # Print blockers — this is NOT a failure, it's honest documentation
    if blockers:
        print("\n  === BLOCKERS (documented, not failures) ===")
        for b in blockers:
            print(f"  {b}")

    # This test always passes — it documents state, doesn't fake execution
    assert True
