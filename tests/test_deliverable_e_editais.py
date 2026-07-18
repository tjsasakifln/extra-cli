"""Tests for Deliverable E open editais recommendations."""
from __future__ import annotations

from scripts.ops.deliverable_e_editais import (
    CLIENT_LABEL,
    DISCLAIMER,
    audit_report,
    build_report,
    fixture_report,
    prove_open,
    recommend,
)


def test_fixture_only_open_with_proof() -> None:
    report = fixture_report()
    assert report.excluded_not_open >= 1
    assert report.recommendations
    for r in report.recommendations:
        assert r["openness"]["is_open_at_cut"] is True
        assert r["ranking"] in {"GO", "REVIEW", "NO_GO"}
        assert r["client_label"] == CLIENT_LABEL[r["ranking"]]
        assert DISCLAIMER[:20] in r["disclaimer"]
        assert r["referencias_oficiais"]
    audited = audit_report(report)
    assert audited["ok"] is True


def test_closed_excluded() -> None:
    closed = {
        "edital_id": "X",
        "status": "CANCELADA",
        "is_open": False,
        "official_url": "http://x",
    }
    assert recommend(closed, "2026-07-18") is None


def test_snapshot_required() -> None:
    bad = {
        "edital_id": "Y",
        "status": "ABERTA",
        "is_open": True,
        "proof_mode": "SNAPSHOT",
        "official_url": "http://y",
    }
    assert prove_open(bad, "2026-07-18") is None


def test_client_labels() -> None:
    assert CLIENT_LABEL["GO"] == "PARTICIPAR"
    assert CLIENT_LABEL["NO_GO"] == "NÃO PARTICIPAR"
    assert CLIENT_LABEL["REVIEW"] == "REVIEW"


def test_empty_report() -> None:
    report = build_report([])
    assert report.status == "EMPTY"
    assert audit_report(report)["ok"] is True


def test_disclaimer_no_victory_promise() -> None:
    report = fixture_report()
    for r in report.recommendations:
        d = r["disclaimer"].lower()
        assert "não promete" in d or "nao promete" in d
        assert "jurídica" in d or "juridica" in d
