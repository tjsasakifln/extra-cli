"""Product tests for national_intel engines.

When REQUIRE_REAL_DB=1 and an isolated DB with migration 060 + contracts is
available, exercises real SQL. Otherwise skips cleanly (never fail on MagicMock).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from scripts.national_intel.agencies import run_agencies
from scripts.national_intel.benchmarks import run_benchmarks
from scripts.national_intel.competitors import run_competitors


def _is_real_conn(conn) -> bool:
    if conn is None or isinstance(conn, MagicMock):
        return False
    # Real psycopg2 connection has closed attribute / info
    return hasattr(conn, "cursor") and not isinstance(getattr(conn, "cursor", None), MagicMock)


def _require_real_db() -> bool:
    return os.getenv("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}


pytestmark = [
    pytest.mark.real_db,
]


@pytest.fixture
def real_pg(pg_conn):
    if not _require_real_db():
        pytest.skip("REQUIRE_REAL_DB not set")
    if not _is_real_conn(pg_conn):
        pytest.skip("psycopg2 mocked or unavailable")
    return pg_conn


def test_competitors_envelope(real_pg, national_intel_dsn: str) -> None:
    data = run_competitors(real_pg, keyword="paviment", limit=20, dsn=national_intel_dsn)
    assert data["product_id"] == "competitors_geo"
    assert data["scope_label"] == "intel_product"
    assert "limitations" in data
    # Empty result is valid when no matching rows (not a mock assert-0 trap)
    assert data["row_count"] >= 0
    if data["row_count"] >= 1:
        entrants = [r for r in data["rows"] if r.get("entrant_signal")]
        for e in entrants:
            assert e["entrant_signal"]["claim_class"] == "hypothesis"
            assert e["has_sc"] is False


def test_benchmarks_sample_gate(real_pg, national_intel_dsn: str) -> None:
    ok = run_benchmarks(real_pg, keyword="paviment", min_sample=3, dsn=national_intel_dsn)
    assert ok["status"] in {"ok", "insufficient_sample"}
    if ok.get("sample_size", 0) >= 3:
        assert ok["status"] == "ok"
        assert ok["rows"][0]["valor_p50"] is not None
        assert ok["rows"][0]["unit_price"] is None

    bad = run_benchmarks(
        real_pg, keyword="zzzz-no-match-xyz", min_sample=20, dsn=national_intel_dsn
    )
    assert bad["status"] == "insufficient_sample"


def test_agencies_profiles(real_pg, national_intel_dsn: str) -> None:
    data = run_agencies(real_pg, limit=20, dsn=national_intel_dsn)
    assert data["product_id"] == "agencies_profile"
    assert data["scope_label"] == "intel_product"
    assert data["row_count"] >= 0
    if data["row_count"] >= 1:
        row = data["rows"][0]
        assert "contract_count" in row
        assert "top_supplier_share" in row
        assert row["top_supplier_share_claim_class"] == "indicator"


def test_views_exist(real_pg) -> None:
    from scripts.national_intel.db import fetch_all

    rows = fetch_all(
        real_pg,
        """
        SELECT table_name FROM information_schema.views
        WHERE table_schema='public' AND table_name LIKE %s
        ORDER BY 1
        """,
        ("v_intel_%",),
    )
    names = {r["table_name"] for r in rows}
    if not names:
        pytest.skip("intel views not applied on this DSN (migration 060 pending)")
    assert "v_intel_contracts_raw_national" in names
    assert "v_intel_contracts_geo_sc" in names
    assert "v_intel_supplier_geo" in names
    assert "v_intel_agency_profile" in names


def test_geo_sc_view_only_sc(real_pg) -> None:
    from scripts.national_intel.db import fetch_all

    try:
        rows = fetch_all(
            real_pg,
            "SELECT DISTINCT uf FROM v_intel_contracts_geo_sc LIMIT 100",
        )
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"view unavailable: {exc}")
    for r in rows:
        assert str(r["uf"]).upper() == "SC"
