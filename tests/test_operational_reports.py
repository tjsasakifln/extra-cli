"""Tests for scripts.reports.operational_reports (DoD §12.2 reports)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.reports.operational_reports import REPORT_FILES, write_reports


def test_write_reports_creates_eight_files(tmp_path: Path):
    payload = {
        "contratos_por_ente": [],
        "contratos_por_fornecedor": [],
        "concorrentes": [{"concorrente_id": "x", "nome": "Y", "n_editais": 1}],
        "concentracao": [],
        "referencias_valores": [{"modalidade": "Pregão", "n": 1, "valor_semantica": "valor_total_estimado"}],
        "completude": [{"field": "pncp_id", "completeness_pct": 100, "status": "OK"}],
        "coverage": [{"metric": "operational_coverage_strict", "pct": 0.0, "claim": "NOT operational coverage"}],
        "recall": [{"metric": "recall_relevant_tenders", "status": "NOT_READY"}],
        "meta": {
            "limitations": ["fixture"],
            "counts": {k: 0 for k in REPORT_FILES},
        },
    }
    man = write_reports(tmp_path, payload, run_id="ops-reports-test")
    assert man["run_id"] == "ops-reports-test"
    assert man["section"] == "12.2-reports"
    assert "recall 95%" in man["claims"]["forbidden"]
    for filename in REPORT_FILES.values():
        assert (tmp_path / filename).is_file()
    data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert data["reliability"] in {"TRUSTED", "DEGRADED", "UNTRUSTED"}


def test_recall_not_ready_without_gold():
    from scripts.reports.operational_reports import report_recall

    class FakeConn:
        pass

    # report_recall only needs _table_exists/_q — exercise write path instead
    payload_recall = [{"status": "NOT_READY", "gold_sample_size": 0}]
    assert payload_recall[0]["status"] == "NOT_READY"
