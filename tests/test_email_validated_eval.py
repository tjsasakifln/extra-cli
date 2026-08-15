"""Evaluator and stop-the-line gate drive the shipped promotion function."""

from __future__ import annotations

from pathlib import Path

from scripts.decision_unit_intelligence.email_validated.evaluate import evaluate_gold_set, regression_gate
from scripts.decision_unit_intelligence.email_validated.policy import POLICY_VERSION
from scripts.decision_unit_intelligence.email_validated.schema import GOLD_SET_VERSION, load_jsonl

GOLD_PATH = Path("evals/email_validated/gold/gold-set.v1.jsonl")
STOP_PATH = Path("evals/email_validated/fixtures/stop-the-line-wrong-person.jsonl")


def test_evaluate_gold_set_is_deterministic_and_reports_primary_metric():
    records = load_jsonl(GOLD_PATH)
    first = evaluate_gold_set(records)
    second = evaluate_gold_set(records)
    assert first == second
    assert first["policy_version"] == POLICY_VERSION
    assert first["gold_set_version"] == GOLD_SET_VERSION
    assert first["primary_metric"] == "precision_email_validated"
    assert first["n"] >= 50
    assert first["precision_email_validated"] is None
    assert first["precision_denominator"] == "no predicted positives"
    assert first["false_positives"] == 0
    assert isinstance(first["abstention"], int)
    assert first["abstention"] == first["n"]
    assert first["provenance_completeness"] is not None
    assert first["stale_rate"] is not None
    assert first["by_source"]
    assert first["by_engine"]
    assert first["auto_send"] is False
    assert first["stop_the_line"] is False
    gate = regression_gate(first)
    assert gate["passed"] is True
    assert gate["stop_the_line"] is False


def test_stop_the_line_fixture_promotes_wrong_person_and_wrong_company():
    records = load_jsonl(STOP_PATH)
    report = evaluate_gold_set(records)
    assert report["stop_the_line"] is True
    assert report["stop_the_line_count"] >= 1
    classes = {item["human_verdict"] for item in report["stop_the_line_cases"]}
    assert "WRONG_PERSON" in classes
    assert "WRONG_COMPANY" in classes
    gate = regression_gate(report)
    assert gate["passed"] is False
    assert gate["stop_the_line"] is True
    assert "WRONG_PERSON" in gate["classes"]
    assert "WRONG_COMPANY" in gate["classes"]
