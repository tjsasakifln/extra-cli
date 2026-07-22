"""Fixture-backed product tests on isolated DB (5435)."""

from __future__ import annotations

import pytest

from scripts.national_intel.agencies import run_agencies
from scripts.national_intel.benchmarks import run_benchmarks
from scripts.national_intel.competitors import run_competitors


def test_competitors_multi_uf_and_entrant_hypothesis(pg_conn, national_intel_dsn: str) -> None:
    data = run_competitors(pg_conn, keyword="paviment", limit=20, dsn=national_intel_dsn)
    assert data["product_id"] == "competitors_geo"
    assert data["scope_label"] == "intel_product"
    assert data["row_count"] >= 1
    assert data["limitations"]
    # CONCORRENTE SUL should appear with SC+PR when fixtures loaded
    names = {r.get("fornecedor_nome") for r in data["rows"]}
    if "CONCORRENTE SUL LTDA" in names:
        row = next(r for r in data["rows"] if r["fornecedor_nome"] == "CONCORRENTE SUL LTDA")
        assert row["has_sc"] is True
        assert row["uf_count"] >= 2
        assert "SC" in (row.get("ufs") or [])
    # entrant without SC
    entrants = [r for r in data["rows"] if r.get("entrant_signal")]
    for e in entrants:
        assert e["entrant_signal"]["claim_class"] == "hypothesis"
        assert e["has_sc"] is False


def test_benchmarks_sample_gate(pg_conn, national_intel_dsn: str) -> None:
    ok = run_benchmarks(
        pg_conn, keyword="paviment", min_sample=3, dsn=national_intel_dsn
    )
    assert ok["status"] in {"ok", "insufficient_sample"}
    if ok["sample_size"] >= 3:
        assert ok["status"] == "ok"
        assert ok["rows"][0]["valor_p50"] is not None
        assert ok["rows"][0]["unit_price"] is None

    bad = run_benchmarks(
        pg_conn, keyword="zzzz-no-match-xyz", min_sample=20, dsn=national_intel_dsn
    )
    assert bad["status"] == "insufficient_sample"
    assert bad["rows"][0]["sample_size"] == 0


def test_agencies_profiles(pg_conn, national_intel_dsn: str) -> None:
    data = run_agencies(pg_conn, limit=20, dsn=national_intel_dsn)
    assert data["product_id"] == "agencies_profile"
    assert data["scope_label"] == "intel_product"
    assert data["row_count"] >= 1
    row = data["rows"][0]
    assert "contract_count" in row
    assert "top_supplier_share" in row
    assert row["top_supplier_share_claim_class"] == "indicator"


def test_views_exist(pg_conn) -> None:
    from scripts.national_intel.db import fetch_all

    rows = fetch_all(
        pg_conn,
        """
        SELECT table_name FROM information_schema.views
        WHERE table_schema='public' AND table_name LIKE %s
        ORDER BY 1
        """,
        ("v_intel_%",),
    )
    names = {r["table_name"] for r in rows}
    assert "v_intel_contracts_raw_national" in names
    assert "v_intel_contracts_geo_sc" in names
    assert "v_intel_supplier_geo" in names
    assert "v_intel_agency_profile" in names


def test_geo_sc_view_only_sc(pg_conn) -> None:
    from scripts.national_intel.db import fetch_all

    rows = fetch_all(
        pg_conn,
        "SELECT DISTINCT uf FROM v_intel_contracts_geo_sc",
    )
    for r in rows:
        assert str(r["uf"]).upper() == "SC"
