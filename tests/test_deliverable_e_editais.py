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
    score_against_profile,
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
    """Non-operational audit may still inspect EMPTY structure."""
    report = build_report([])
    assert report.status == "EMPTY"
    assert audit_report(report)["ok"] is True


def test_empty_report_operational_fail_closed() -> None:
    """Operational acceptance must not pass on an empty recommendation set."""
    report = build_report([])
    audited = audit_report(report, operational=True)
    assert audited["ok"] is False
    assert any(
        c["item_id"] == "non_empty_operational" and c["status"] == "FAIL"
        for c in audited["checks"]
    )


def test_pending_capacity_never_go() -> None:
    """ADR-022: critical PENDING capacity must not yield GO/PARTICIPAR."""
    ranking, fav, risk, notes = score_against_profile(
        {
            "uf": "SC",
            "objeto": "reforma predial de edificacao publica",
            "official_url": "https://pncp.gov.br/e/1",
            "status": "ABERTA",
        },
        {
            "region": {"uf_primary": "SC"},
            "engineering_categories": ["reforma_predial"],
            "hard_blocks": {},
            "elicitation": {
                "capital_giro": {"status": "PENDING", "value": None},
                "capacidade_simultanea": {"status": "PENDING", "value": None},
                "capacidade_garantia": {"status": "PENDING", "value": None},
                "cats_atestados": {"status": "PENDING", "value": []},
                "certidoes": {"status": "PENDING", "value": None},
            },
        },
    )
    assert ranking == "REVIEW"
    assert any("PENDING" in r for r in risk)
    assert CLIENT_LABEL[ranking] == "REVIEW"


def test_complete_capacity_can_go() -> None:
    ranking, fav, risk, _notes = score_against_profile(
        {
            "uf": "SC",
            "objeto": "reforma predial de edificacao publica",
            "official_url": "https://pncp.gov.br/e/1",
            "status": "ABERTA",
        },
        {
            "region": {"uf_primary": "SC"},
            "engineering_categories": ["reforma_predial"],
            "hard_blocks": {},
            "elicitation": {
                "capital_giro": {"status": "SET", "value": 500_000},
                "capacidade_simultanea": {"status": "SET", "value": 3},
                "capacidade_garantia": {"status": "SET", "value": 200_000},
                "cats_atestados": {"status": "SET", "value": ["CAT-1"]},
                "certidoes": {"status": "SET", "value": "ok"},
            },
            "capital_giro": 500_000,
            "capacidade_simultanea": 3,
            "capacidade_garantia": 200_000,
            "cats_atestados": ["CAT-1"],
            "certidoes": "ok",
        },
    )
    assert ranking == "GO"
    assert fav
    assert not any("PENDING" in r for r in risk)


def test_disclaimer_no_victory_promise() -> None:
    report = fixture_report()
    for r in report.recommendations:
        d = r["disclaimer"].lower()
        assert "não promete" in d or "nao promete" in d
        assert "jurídica" in d or "juridica" in d


def test_live_loader_and_from_db_api_exist() -> None:
    from scripts.ops import deliverable_e_editais as m

    assert callable(m.load_open_candidates_from_db)
    assert callable(m.build_report_from_db)
    # CLI exposes operational commands
    src = open(m.__file__, encoding="utf-8").read()
    assert "from-db" in src and "audit-db" in src
