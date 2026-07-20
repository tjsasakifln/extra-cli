"""Honest spike reclassification tests (skeptic remediation)."""
from __future__ import annotations

from scripts.architecture.spike_e_dbt_honest import evaluate_dbt_spike
from scripts.architecture.spike_g_documents_honest import evaluate_document_parser_spike


def test_dbt_spike_is_rejected_without_experiment() -> None:
    r = evaluate_dbt_spike()
    assert r["decision"] == "REJECTED_WITHOUT_EXPERIMENT"
    assert r["experiment_run"] is False
    assert r["corpus_opportunities"] == 0
    assert r["production_dep_added"] is False


def test_document_spike_deferred_without_corpus() -> None:
    r = evaluate_document_parser_spike()
    assert r["decision"] == "DEFERRED_NO_CORPUS"
    assert r["gaps"]["scanned"] == 5
    assert r["production_dep_added"] is False


def test_document_spike_ready_when_corpus_met() -> None:
    full = {k: 5 for k in ("digital_simple", "multicolumn", "tables", "scanned")}
    r = evaluate_document_parser_spike(corpus_counts=full)
    assert r["decision"] == "READY_FOR_ENGINE_COMPARISON"
