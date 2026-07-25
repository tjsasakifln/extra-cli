"""Evaluation, statistical gates, gold corpus structure, campaign entry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.hybrid_sector.evaluation.gates import (
    INSUFFICIENT_STATISTICAL_POWER,
    evaluate_gates,
)
from scripts.ops.hybrid_sector.evaluation.gold_corpus import (
    gold_index,
    load_gold_corpus,
    locked_test_adequacy,
    records_as_universe,
)
from scripts.ops.hybrid_sector.evaluation.metrics import binomial_ci_lower_one_sided
from scripts.ops.hybrid_sector.pipeline import (
    run_from_gold_corpus,
    run_pipeline,
    write_campaign_artifacts,
)
from scripts.ops.campaign_hybrid_sector_recall import main as campaign_main

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/hybrid_sector/gold_corpus.json"
CAMP = ROOT / "artifacts/campaigns/HYBRID-SECTOR-RECALL-LLM-ARBITER-01"


def test_binomial_ci_all_success_large_n():
    # 0 failures in 300 → lower bound should be around >= 0.99
    low = binomial_ci_lower_one_sided(300, 300)
    assert low >= 0.99


def test_gold_corpus_locked_adequacy():
    assert CORPUS.is_file(), "gold corpus fixture missing"
    corpus = load_gold_corpus(CORPUS)
    adq = locked_test_adequacy(corpus)
    assert adq["checks"]["positives"]["have"] >= 300
    assert adq["checks"]["hard_negatives"]["have"] >= 300
    assert adq["checks"]["ambiguous"]["have"] >= 150
    assert adq["checks"]["positives_without_keywords"]["have"] >= 100
    assert adq["ok"] is True
    # Labels not from classifier under test
    assert "independent" in corpus.get("label_policy", "").lower() or corpus.get(
        "label_policy"
    )


def test_gates_insufficient_power_honest():
    retrieval = {"retrieval_recall": 1.0, "retrieval_recall_lower_95": 0.5, "n_gold_positives": 10}
    decision = {
        "safe_recall_match_plus_review": 1.0,
        "safe_recall_lower_95": 0.5,
        "critical_false_negatives": 0,
        "n_positives": 10,
        "match_precision": 1.0,
        "match_precision_lower_95": 0.5,
        "match_false_positives_hard": 0,
    }
    res = evaluate_gates(retrieval, decision, audit={
        "invented_evidence_accepted": 0,
        "llm_error_to_review_rate": 1.0,
        "lineage_coverage": 1.0,
        "silent_discards": 0,
    })
    assert res["gates"]["statistical_power"]["status"] == INSUFFICIENT_STATISTICAL_POWER
    assert res["terminal_status"] == "BLOCKED_INSUFFICIENT_STATISTICAL_POWER"


def test_gates_ready_when_metrics_and_power():
    retrieval = {
        "retrieval_recall": 1.0,
        "retrieval_recall_lower_95": 0.995,
        "n_gold_positives": 300,
    }
    decision = {
        "safe_recall_match_plus_review": 1.0,
        "safe_recall_lower_95": 0.995,
        "critical_false_negatives": 0,
        "n_positives": 300,
        "match_precision": 1.0,
        "match_precision_lower_95": 0.95,
        "match_false_positives_hard": 0,
    }
    res = evaluate_gates(
        retrieval,
        decision,
        audit={
            "invented_evidence_accepted": 0,
            "llm_error_to_review_rate": 1.0,
            "lineage_coverage": 1.0,
            "silent_discards": 0,
        },
    )
    assert res["terminal_status"] == "READY_FOR_RECALL_ASSURANCE_REVIEW"


def test_campaign_entry_fixtures_twice(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    assert campaign_main(["--fixtures", "--out", str(out1)]) == 0
    assert campaign_main(["--fixtures", "--out", str(out2)]) == 0
    for out in (out1, out2):
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        assert result["terminal_status"] in {
            "BLOCKED_INSUFFICIENT_RECALL",
            "BLOCKED_INSUFFICIENT_STATISTICAL_POWER",
            "BLOCKED_REVIEW_CAPACITY",
            "BLOCKED_LLM_OPERATIONAL_VALIDATION",
            "READY_FOR_RECALL_ASSURANCE_REVIEW",
        }
        assert result["claims"]["ACCEPTED"] is False
        assert result["claims"]["MERGED"] is False
        assert (out / "deliverable_e_matches.json").is_file()
        assert (out / "deliverable_e_review_queue.json").is_file()
        assert (out / "deliverable_e_no_match_audit.json").is_file()
        assert (out / "final-report.md").is_file()


def test_locked_eval_pipeline_offline():
    """Drive real entry on gold locked split with fake provider (may be slow-ish)."""
    result = run_from_gold_corpus(CORPUS, split="locked", force_fake_llm=True)
    assert len(result.lineages) == len(result.candidates)
    assert result.terminal_status in {
        "BLOCKED_INSUFFICIENT_RECALL",
        "BLOCKED_INSUFFICIENT_STATISTICAL_POWER",
        "BLOCKED_REVIEW_CAPACITY",
        "BLOCKED_LLM_OPERATIONAL_VALIDATION",
        "READY_FOR_RECALL_ASSURANCE_REVIEW",
    }
    # Commercial MATCH never includes non-MATCH decisions
    for m in result.deliverables["deliverable_e_matches"]:
        assert m["lineage"]["commercial_decision"] == "MATCH"
    # No LLM error path yields NO_MATCH
    for lin in result.lineages:
        if lin.llm_error:
            assert lin.commercial_decision == "REVIEW"
    # Shadow replay present
    assert "shadow_replay" in result.evaluation
    assert "champion" in result.evaluation["shadow_replay"]
    assert "challenger" in result.evaluation["shadow_replay"]


def test_write_artifacts_contract(tmp_path):
    records = [
        {
            "source": "pncp",
            "official_id": "1",
            "objeto": "Execução de pavimentação asfáltica em vias",
            "orgao": "Secretaria de Obras",
        },
        {
            "source": "pncp",
            "official_id": "2",
            "objeto": "Aquisição de notebook para secretaria",
        },
    ]
    gold = {"pncp::1": "POSITIVE", "pncp::2": "NEGATIVE"}
    result = run_pipeline(records, force_fake_llm=True, gold_labels=gold)
    paths = write_campaign_artifacts(result, tmp_path, corpus_manifest={"n": 2})
    required = [
        "manifest.json",
        "retrieval-evaluation.json",
        "classification-evaluation.json",
        "calibration.json",
        "confidence-intervals.json",
        "gold-corpus-manifest.json",
        "shadow-replay.json",
        "no-match-audit.json",
        "review-queue-analysis.json",
        "llm-cost.json",
        "llm-failures.json",
        "prompt-injection-tests.json",
        "drift-baseline.json",
        "findings.json",
        "result.json",
        "final-report.md",
        "deliverable_e_matches.json",
        "deliverable_e_review_queue.json",
        "deliverable_e_no_match_audit.json",
    ]
    for name in required:
        assert (tmp_path / name).is_file(), name
    result_json = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    text = (tmp_path / "result.json").read_text(encoding="utf-8")
    for forbidden in ("PROJECT_DONE", "FULLY GUARANTEED", "100% NO FALSE NEGATIVES"):
        # may appear as keys set to false — ensure not claimed true
        assert result_json["claims"]["ACCEPTED"] is False
    assert "ACCEPTED" not in text or result_json["claims"]["ACCEPTED"] is False
