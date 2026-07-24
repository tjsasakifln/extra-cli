"""Tests for EXTRA-LIVE-CONSULTING-PACK-01 live consulting pack.

Unit tests drive shipped functions. Isolation and schema collision are
structural. Full population path runs when CAMPAIGN_TEST_DSN has data.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

from scripts.ops import live_consulting_pack as lcp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_DSN = os.getenv(
    "CAMPAIGN_TEST_DSN",
    "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc",
)


def test_mask_dsn_hides_password() -> None:
    masked = lcp.mask_dsn("postgresql://test:secret@127.0.0.1:5436/db")
    assert "secret" not in masked
    assert "test" in masked
    assert "***" in masked


def test_assert_isolation_accepts_local() -> None:
    r = lcp.assert_isolation("postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc")
    assert r["isolation_ok"] is True
    assert r["production_touched"] is False


def test_assert_isolation_rejects_prod_markers() -> None:
    with pytest.raises(SystemExit) as ei:
        lcp.assert_isolation("postgresql://u:p@ec-prod:5432/extra_prod")
    assert "ISOLATION_FAIL" in str(ei.value)


def test_assert_isolation_rejects_non_local_host() -> None:
    with pytest.raises(SystemExit):
        lcp.assert_isolation("postgresql://u:p@db.example.com:5432/x")


def test_migration_060_exists_and_059_coverage_preserved() -> None:
    m060 = PROJECT_ROOT / "db/migrations/060_national_contracts_intelligence_layers.sql"
    m059 = PROJECT_ROOT / "db/migrations/059_coverage_evidence_canonical_entity_unique.sql"
    bad = PROJECT_ROOT / "db/migrations/059_national_contracts_intelligence_layers.sql"
    assert m060.is_file(), "intel layers must be renumbered to 060"
    assert m059.is_file(), "coverage spine 059 must remain"
    assert not bad.exists(), "must not collide with 059 coverage migration"
    text = m060.read_text(encoding="utf-8")
    assert "v_intel_contracts_raw_national" in text
    assert "NOT operational" in text or "NOT operational SC coverage" in text


def test_live_pack_module_entrypoint_registered() -> None:
    assert hasattr(lcp, "run_pack")
    assert hasattr(lcp, "main")
    # structural: package final + deliverables importable
    from scripts.ops import deliverable_a_org_ranking as a
    from scripts.ops import deliverable_b_competitors as b
    from scripts.ops import deliverable_package_final as pkg

    assert callable(a.build_report_from_rows)
    assert callable(b.select_competitors)
    assert callable(pkg.reconcile_package)


def test_national_intel_is_internal_engine() -> None:
    from scripts.national_intel import agencies, competitors

    assert callable(agencies.run_agencies)
    assert callable(competitors.run_competitors)


def _db_has_contracts(dsn: str) -> int:
    try:
        conn = lcp.connect(dsn)
        try:
            n = lcp.scalar(
                conn,
                "SELECT COUNT(*) FROM pncp_supplier_contracts WHERE COALESCE(is_active,TRUE)",
            )
            return int(n or 0)
        finally:
            conn.close()
    except Exception:
        return 0


@pytest.mark.real_db
@pytest.mark.skipif(
    _db_has_contracts(CAMPAIGN_DSN) < 100
    or os.getenv("REQUIRE_REAL_DB", "").lower() not in {"1", "true", "yes"},
    reason="isolated campaign DB not restored or REQUIRE_REAL_DB not set",
)
def test_population_stats_full_not_sample(tmp_path: Path) -> None:
    conn = lcp.connect(CAMPAIGN_DSN)
    try:
        pop = lcp.population_stats(conn, uf="SC")
    finally:
        conn.close()
    assert pop["eligible_population"] >= 100
    assert pop["sample_label"] == "FULL_ELIGIBLE_POPULATION"
    assert pop["not_sample_of_n"] is True


@pytest.mark.real_db
@pytest.mark.skipif(
    _db_has_contracts(CAMPAIGN_DSN) < 100
    or os.getenv("REQUIRE_REAL_DB", "").lower() not in {"1", "true", "yes"},
    reason="isolated campaign DB not restored or REQUIRE_REAL_DB not set",
)
def test_run_pack_end_to_end_real_path(tmp_path: Path) -> None:
    """Drive shipped run_pack on isolated DSN — not fixtures as universe."""
    out = tmp_path / "pack"
    pack = lcp.run_pack(
        dsn=CAMPAIGN_DSN,
        out_dir=out,
        uf="SC",
        export_limit=50,
        target_competitors=15,
        as_of=date(2026, 7, 23),
    )
    assert pack["production_touched"] is False
    assert pack["reconcile"]["status"] == "PASS"
    assert pack["population"]["eligible_population"] >= 100
    assert pack["deliverable_a"]["status"] in {"OK", "PARTIAL"}
    assert pack["deliverable_a"]["n_rows"] >= 1
    # B: OK with >=15 or honest INSUFFICIENT
    assert pack["deliverable_b"]["status"] in {"OK", "INSUFFICIENT", "PARTIAL"}
    if pack["deliverable_b"]["status"] == "OK":
        assert int(pack["deliverable_b"]["valid_count"]) >= 15
    assert (out / "extra_live_consulting_pack.xlsx").is_file()
    assert (out / "extra_live_consulting_pack.pdf").is_file()
    assert (out / "pack-manifest.json").is_file()
    # export limit must not silently redefine universe
    a = json.loads((out / "deliverable_a.json").read_text(encoding="utf-8"))
    assert a["population"]["export_is_not_universe"] is True
    assert a["population"]["eligible_population"] == pack["population"]["eligible_population"]


def test_cli_verify_isolation_exit_codes() -> None:
    assert lcp.main(["verify-isolation", "--dsn", "postgresql://t:t@127.0.0.1:5436/x"]) == 0
    assert (
        lcp.main(["verify-isolation", "--dsn", "postgresql://t:t@ec-prod:5432/x"]) == 2
    )
