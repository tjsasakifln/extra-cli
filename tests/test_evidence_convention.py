"""Tests for DoD evidence convention catalog."""
from __future__ import annotations

from scripts.ops.evidence_convention import (
    EVIDENCE_KINDS,
    KIND_IDS,
    audit_evidence_convention,
    catalog,
    classify_evidence,
    item_may_be_marked_complete,
)


def test_ten_kinds_match_dod_section() -> None:
    assert len(EVIDENCE_KINDS) == 10
    assert len(KIND_IDS) == 10
    labels = " ".join(k["label"] for k in EVIDENCE_KINDS)
    assert "teste automatizado" in labels
    assert "exit code" in labels or "exit" in labels
    assert "SQL" in labels or "sql" in labels.lower()
    assert "ledger" in labels or "manifest" in labels
    assert "Tiago" in labels or "manual" in labels
    assert "commit" in labels or "pull" in labels
    assert "restaura" in labels or "recupera" in labels
    assert "fonte oficial" in labels or "oficial" in labels


def test_classify_each_kind_has_positive_example() -> None:
    samples = {
        "automated_test": "pytest tests/test_x.py — 3 passed",
        "documented_command_exit_0": "python -m scripts.ops.x exit code 0",
        "system_report": "output/coverage/report.json gerado pelo sistema",
        "sql_query": "SELECT count(*) FROM entities — sql result matches",
        "run_ledger": "run_id=abc recorded in ledger/manifest",
        "dated_log": "log 2026-07-18 journalctl correlation-id=z",
        "manual_validation_tiago": "validação manual registrada por Tiago",
        "commit_or_pr": "commit 58d9a83a5cac663c PR #27",
        "restore_or_recovery_executed": "pg_restore executed local_backup_restore proof",
        "official_source_comparison": "comparação com fonte oficial na mesma data",
    }
    for kid, sample in samples.items():
        clf = classify_evidence(sample)
        assert kid in clf.kinds, f"{kid} not matched in {clf.kinds} for {sample!r}"
        assert clf.accepted is True


def test_empty_evidence_blocks_completion() -> None:
    r = item_may_be_marked_complete([])
    assert r["allowed"] is False
    r3 = item_may_be_marked_complete(["???"])
    assert r3["allowed"] is False


def test_audit_runs_on_dod() -> None:
    report = audit_evidence_convention("DOD.md")
    assert report["policy"]["complete_requires_at_least_one_kind"] is True
    assert report["checked_total"] > 0
    assert len(report["kinds_catalog"]) == 10


def test_catalog_stable() -> None:
    c = catalog()
    assert c["version"] == "1.0.0"
    assert len(c["kinds"]) == 10
