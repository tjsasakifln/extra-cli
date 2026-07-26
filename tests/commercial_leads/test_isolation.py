"""Isolation fail-closed tests."""

from __future__ import annotations

from scripts.commercial_leads.isolation import assert_isolation


def test_local_campaign_port_ok():
    r = assert_isolation("postgresql://test:test@127.0.0.1:5441/extra_confenge_commercial_01")
    assert r.ok
    assert r.production_touched is False
    assert r.soak_touched is False


def test_prod_host_rejected():
    r = assert_isolation("postgresql://u:p@ec-prod:5432/extra_prod")
    assert not r.ok
    assert r.production_touched is True


def test_port_5432_rejected():
    r = assert_isolation("postgresql://test:test@127.0.0.1:5432/anything")
    assert not r.ok


def test_soak_path_rejected():
    r = assert_isolation(
        "postgresql://test:test@127.0.0.1:5441/db",
        out_dir="/tmp/artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/soak",
    )
    assert not r.ok
    assert r.soak_touched is True
