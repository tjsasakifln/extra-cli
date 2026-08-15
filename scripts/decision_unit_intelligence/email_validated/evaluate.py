"""Offline evaluator for the EMAIL_VALIDATED gold set.

Primary metric is precision of EMAIL_VALIDATED. Promoting WRONG_PERSON or
WRONG_COMPANY is a blocking stop-the-line. Never fetches the web.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts.decision_unit_intelligence.email_validated.policy import (
    POLICY_VERSION,
    PREDICTED_EMAIL_VALIDATED,
    decide_promotion,
)
from scripts.decision_unit_intelligence.email_validated.schema import (
    GOLD_SET_VERSION,
    AdjudicationRecord,
)

STOP_THE_LINE_VERDICTS = frozenset({"WRONG_PERSON", "WRONG_COMPANY"})
GOLD_POSITIVE = "VALIDATED_DIRECT"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def evaluate_gold_set(records: list[AdjudicationRecord]) -> dict[str, Any]:
    """Compare shipped promotion decisions to gold human verdicts."""
    predicted_pos = 0
    gold_pos = 0
    true_pos = 0
    false_pos = 0
    false_neg = 0
    abstentions = 0
    provenance_ok = 0
    stale = 0
    stop_the_line: list[dict[str, Any]] = []
    false_positives: list[dict[str, Any]] = []
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "predicted": 0, "tp": 0, "fp": 0})
    by_engine: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "predicted": 0, "tp": 0, "fp": 0})
    by_verdict: dict[str, int] = defaultdict(int)
    decisions: list[dict[str, Any]] = []

    for record in records:
        decision = decide_promotion(record)
        gold_is_pos = record.human_verdict == GOLD_POSITIVE
        pred_is_pos = decision.promote and decision.predicted_class == PREDICTED_EMAIL_VALIDATED
        by_verdict[record.human_verdict] += 1
        if record.has_provenance() and record.has_source_date():
            provenance_ok += 1
        if record.freshness == "STALE" or record.human_verdict == "OBSERVED_BUT_STALE":
            stale += 1
        if pred_is_pos:
            predicted_pos += 1
        else:
            abstentions += 1
        if gold_is_pos:
            gold_pos += 1
        if pred_is_pos and gold_is_pos:
            true_pos += 1
        if pred_is_pos and not gold_is_pos:
            false_pos += 1
            item = {
                "case_id": record.case_id,
                "human_verdict": record.human_verdict,
                "email": record.email,
                "company": record.company,
                "reasons": list(decision.reasons),
            }
            false_positives.append(item)
            if record.human_verdict in STOP_THE_LINE_VERDICTS:
                stop_the_line.append(item)
        if gold_is_pos and not pred_is_pos:
            false_neg += 1
        bucket_source = by_source[record.source or "unknown"]
        bucket_source["n"] += 1
        bucket_source["predicted"] += int(pred_is_pos)
        bucket_source["tp"] += int(pred_is_pos and gold_is_pos)
        bucket_source["fp"] += int(pred_is_pos and not gold_is_pos)
        bucket_engine = by_engine[record.engine or "unknown"]
        bucket_engine["n"] += 1
        bucket_engine["predicted"] += int(pred_is_pos)
        bucket_engine["tp"] += int(pred_is_pos and gold_is_pos)
        bucket_engine["fp"] += int(pred_is_pos and not gold_is_pos)
        decisions.append(
            {
                "case_id": record.case_id,
                "split": record.split,
                "human_verdict": record.human_verdict,
                "promote": decision.promote,
                "predicted_class": decision.predicted_class,
                "epistemic": decision.epistemic,
                "reasons": list(decision.reasons),
                "engine": record.engine,
                "source": record.source,
            }
        )

    n = len(records)
    precision = _ratio(true_pos, predicted_pos)
    recall = _ratio(true_pos, gold_pos)
    return {
        "schema_id": "confenge.email-validated-eval.v1",
        "policy_version": POLICY_VERSION,
        "gold_set_version": GOLD_SET_VERSION,
        "n": n,
        "primary_metric": "precision_email_validated",
        "precision_email_validated": precision,
        "precision_denominator": "no predicted positives" if predicted_pos == 0 else predicted_pos,
        "recall_email_validated": recall,
        "recall_measurable": gold_pos > 0 and predicted_pos > 0,
        "recall_note": None if gold_pos > 0 else "unmeasurable: gold set has zero VALIDATED_DIRECT (declared skew)",
        "true_positives": true_pos,
        "false_positives": false_pos,
        "false_negatives": false_neg,
        "predicted_positives": predicted_pos,
        "gold_positives": gold_pos,
        "abstention": abstentions,
        "abstention_rate": _ratio(abstentions, n),
        "provenance_completeness": _ratio(provenance_ok, n),
        "stale_rate": _ratio(stale, n),
        "stop_the_line": bool(stop_the_line),
        "stop_the_line_count": len(stop_the_line),
        "stop_the_line_cases": stop_the_line,
        "false_positive_list": false_positives,
        "by_source": {key: _with_precision(val) for key, val in sorted(by_source.items())},
        "by_engine": {key: _with_precision(val) for key, val in sorted(by_engine.items())},
        "by_human_verdict": dict(sorted(by_verdict.items())),
        "auto_send": False,
        "decisions": decisions,
    }


def _with_precision(bucket: dict[str, int]) -> dict[str, Any]:
    predicted = bucket["predicted"]
    return {
        **bucket,
        "precision": _ratio(bucket["tp"], predicted) if predicted else "no predicted positives",
    }


def regression_gate(report: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when WRONG_PERSON / WRONG_COMPANY is promoted."""
    tripped = bool(report.get("stop_the_line"))
    classes = sorted(
        {item.get("human_verdict") for item in report.get("stop_the_line_cases") or [] if item.get("human_verdict")}
    )
    return {
        "passed": not tripped,
        "stop_the_line": tripped,
        "stop_the_line_count": int(report.get("stop_the_line_count") or 0),
        "classes": classes,
        "policy_version": report.get("policy_version"),
        "gold_set_version": report.get("gold_set_version"),
    }
