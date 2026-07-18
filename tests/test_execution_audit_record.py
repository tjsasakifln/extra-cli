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
