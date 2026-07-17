"""Tests for honest commercial sample report + session B2G bundle."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.reports.commercial_b2g_session import (
    _status_bucket,
    build_disclaimers,
    build_session_report,
    write_all,
)
from scripts.reports.commercial_sample_sc import build_report


def test_build_report_has_disclaimers_and_forbidden_claims():
    report = build_report(dsn=None, include_session=True)
    assert report["report"] == "commercial-sample-sc"
    assert report["confidence"] in {"low", "low_to_medium", "medium", "high"}
    assert isinstance(report["disclaimers"], list)
    assert len(report["disclaimers"]) >= 2
    forbidden = " ".join(report["claims_forbidden"]).lower()
    assert "90d" in forbidden or "3 anos" in forbidden or "3y" in forbidden or "backfill" in forbidden
    # Must not claim full pilot success in allowed claims when artifact is partial
    pilot = json.loads(Path("output/contracts/pilot-90d-next30d.json").read_text(encoding="utf-8"))
    if pilot.get("status") == "partial":
        assert report["contracts_pilot"]["status"] == "partial"
        assert report["contracts_pilot"]["go_no_go_3y"] == "NO-GO"


def test_db_unavailable_soft_fails():
    report = build_report(dsn=None, include_session=False)
    assert report["db_sample"]["available"] is False


def test_session_sources_present_when_artifacts_exist():
    report = build_report(dsn=None, include_session=True)
    ss = report.get("session_sources") or {}
    # At least one session source path should resolve if workspace has outputs
    sc_dir = Path("output/sc_compras")
    if sc_dir.is_dir() and any(sc_dir.glob("sc_compras-*/artifact.json")):
        assert ss.get("sc_compras") is not None
        assert ss["sc_compras"].get("available") is True
        assert ss["sc_compras"].get("live_fetch") is True
        assert isinstance(report["opportunities"]["open_sample"], list)
        # Gaps must not be hidden
        gaps = report["opportunities"].get("gaps_in_sample") or {}
        assert "missing_documentos" in gaps or report["opportunities"]["open_sample"] == []
    # Disclaimers must mention partial/coverage honesty when low coverage
    disc = " ".join(report["disclaimers"]).lower()
    assert "cobertura" in disc or "freshness" in disc or "parcial" in disc or "partial" in disc


def test_status_bucket_open_closed():
    assert _status_bucket("Em Recebimento de Proposta") == "open"
    assert _status_bucket("Aguardando Abertura da Sessão") == "open"
    assert _status_bucket("Homologado") == "closed"
    assert _status_bucket("Fracassado") == "closed"
    assert _status_bucket("Aguardando Homologação") == "semi_open"


def test_build_session_report_evidence_chain_and_flags():
    session = build_session_report(dsn=None)
    assert session["report"] == "commercial-b2g-session-sc"
    assert session.get("run_id")
    assert isinstance(session.get("evidence_chain"), list)
    assert len(session["evidence_chain"]) >= 3
    lf = session.get("live_fetch_summary") or {}
    assert "sc_compras" in lf
    assert "coverage_metrics" in lf
    assert lf.get("coverage_metrics") is False  # attestation, not live
    assert isinstance(session.get("disclaimers"), list)
    assert len(session["disclaimers"]) >= 3
    # Forbidden claims present
    forb = " ".join(session["claims_forbidden"]).lower()
    assert "95" in forb or "universo" in forb


def test_disclaimers_expose_missing_docs_when_sample_empty_docs():
    coverage = {
        "editais_crude_pct": 4.76,
        "pilot_status": "partial",
        "coverage_truth": {"monitoring_pct_display": "unverified"},
        "freshness_gate": {"failing_sources": ["pncp"]},
    }
    sc = {
        "available": True,
        "live_fetch": True,
        "mode": "incremental",
        "artifact": {
            "metrics": {
                "api_total_elementos_reported": 2602,
                "fetch_detail": False,
            }
        },
        "opportunities": {
            "total_records": 10,
            "gaps_in_sample": {
                "missing_documentos": 10,
                "pct_missing_documentos": 100.0,
                "pct_missing_valor": 100.0,
                "pct_missing_municipio": 100.0,
            },
        },
    }
    notes = build_disclaimers(
        coverage=coverage,
        sc=sc,
        dom={"available": False},
        doe={"available": False},
        db={"available": False, "reason": "no DSN"},
        recon={"available": False},
    )
    blob = " ".join(notes).lower()
    assert "documentos" in blob
    assert "2602" in blob or "parcial" in blob
    assert "4.76" in blob or "cobertura" in blob


def test_write_all_produces_json_csv_html(tmp_path: Path):
    session = build_session_report(dsn=None)
    paths = write_all(session, output_dir=tmp_path, basename="test-commercial")
    assert Path(paths["json"]).is_file()
    assert Path(paths["csv"]).is_file()
    assert Path(paths["html"]).is_file()
    assert Path(paths["meta"]).is_file()
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert data["run_id"] == session["run_id"]
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert "Disclaimers" in html or "disclaimer" in html.lower()
    assert session["run_id"] in html
