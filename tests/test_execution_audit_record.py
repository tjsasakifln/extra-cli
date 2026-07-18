"""DoD §29 — each execution carries run_id, code/schema versions, etc."""
from __future__ import annotations

from scripts.crawl.run_evidence import (
    EXECUTION_AUDIT_REQUIRED_FIELDS,
    build_execution_audit_record,
    validate_execution_audit_record,
)


def test_required_fields_constant() -> None:
    assert "run_id" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "code_version" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "schema_version" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "spreadsheet_hash" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "source" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "capability" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "parameters" in EXECUTION_AUDIT_REQUIRED_FIELDS
    assert "period" in EXECUTION_AUDIT_REQUIRED_FIELDS


def test_build_execution_audit_record_has_all_fields() -> None:
    rec = build_execution_audit_record(
        source="pncp",
        capability="open_tenders",
        parameters={"mode": "incremental", "days": 3},
        period={"from": "2026-07-01", "to": "2026-07-18"},
    )
    assert rec["run_id"]
    assert rec["code_version"]
    assert rec["schema_version"]
    assert rec["source"] == "pncp"
    assert rec["capability"] == "open_tenders"
    assert rec["parameters"]["mode"] == "incremental"
    assert rec["period"]["from"] == "2026-07-01"
    report = validate_execution_audit_record(rec)
    assert report["ok"] is True, report


def test_validate_detects_missing_source() -> None:
    rec = build_execution_audit_record(
        source="pncp",
        capability="contracts",
        parameters={},
        period="2024-2026",
    )
    del rec["source"]
    report = validate_execution_audit_record(rec)
    assert report["ok"] is False
    assert any("source" in i for i in report["issues"])


def test_execution_record_has_timestamps_status_counts_errors_provenance() -> None:
    rec = build_execution_audit_record(
        source="pncp",
        capability="open_tenders",
        parameters={"mode": "full"},
        period={"days": 7},
        status="success",
        counts_before={"bids": 0},
        counts_after={"bids": 10},
        errors=[],
        checkpoint_path="data/checkpoints/pncp.json",
    )
    assert rec["started_at"]
    assert rec["completed_at"]
    assert rec["status"] == "success"
    assert rec["counts_after"]["bids"] == 10
    assert isinstance(rec["errors"], list)
    assert rec["provenance"]["run_id"] == rec["run_id"]
    report = validate_execution_audit_record(rec, require_outcome=True)
    assert report["ok"] is True, report


def test_report_references_source_runs() -> None:
    from scripts.crawl.run_evidence import attach_report_source_runs

    report = attach_report_source_runs({"title": "weekly"}, ["run-1", "run-2"])
    assert report["source_run_ids"] == ["run-1", "run-2"]
    try:
        attach_report_source_runs({"title": "bad"}, [])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
