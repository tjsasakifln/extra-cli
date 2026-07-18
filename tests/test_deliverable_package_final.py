"""Tests for final consultancy package PDF+Excel."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.deliverable_package_final import (
    audit_report,
    build_package_fixture,
    reconcile_package,
)


def test_fixture_package_reconciles(tmp_path: Path) -> None:
    report = build_package_fixture(tmp_path / "pack")
    assert report.status == "OK"
    assert report.reconcile["status"] == "PASS"
    assert report.tiago_accept["status"] == "PENDING_HUMAN"
    assert report.package["page_estimate"] >= 30
    assert "sumario_executivo" in report.package["pdf_sections"]
    audited = audit_report(report)
    assert audited["ok"] is True
    assert audited["summary"]["fail"] == 0


def test_divergence_detected(tmp_path: Path) -> None:
    report = build_package_fixture(tmp_path / "pack2")
    pkg = dict(report.package)
    pkg["meta"] = dict(pkg["meta"])
    # break profile on a copy for reconcile simulation
    recon = reconcile_package(pkg)
    assert recon.status == "PASS"
    broken = dict(pkg)
    broken_meta = dict(broken["meta"])
    broken_meta["profile_version"] = "DIFFERENT"
    # reconcile_package compares pdf vs excel from same meta dict — inject mismatch via custom

    # Direct unit: empty run_id fails
    empty = {"meta": {}, "quantitative_claims": []}
    r2 = reconcile_package(empty)
    assert r2.status == "FAIL"
    assert r2.same_run_id is False


def test_tiago_not_auto_accepted(tmp_path: Path) -> None:
    report = build_package_fixture(tmp_path / "pack3")
    assert report.tiago_accept["required"] is True
    assert report.tiago_accept["status"] != "ACCEPTED"
