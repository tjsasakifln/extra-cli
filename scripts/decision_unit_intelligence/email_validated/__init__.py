"""Versioned EMAIL_VALIDATED promotion policy and gold-set evaluation.

Gold labels are benchmark verdicts. They are not send authorization and
they are not HUMAN_REVIEW_APPROVED.
"""

from scripts.decision_unit_intelligence.email_validated.evaluate import (
    STOP_THE_LINE_VERDICTS,
    evaluate_gold_set,
    regression_gate,
)
from scripts.decision_unit_intelligence.email_validated.policy import (
    POLICY_ID,
    POLICY_VERSION,
    decide_promotion,
    load_policy_document,
    policy_diff,
)
from scripts.decision_unit_intelligence.email_validated.schema import (
    GOLD_SET_VERSION,
    HUMAN_VERDICTS,
    AdjudicationRecord,
    HumanVerdict,
    PromotionDecision,
    evidence_pack,
    load_jsonl,
    validate_record,
    write_jsonl,
)

__all__ = [
    "GOLD_SET_VERSION",
    "HUMAN_VERDICTS",
    "POLICY_ID",
    "POLICY_VERSION",
    "STOP_THE_LINE_VERDICTS",
    "AdjudicationRecord",
    "HumanVerdict",
    "PromotionDecision",
    "decide_promotion",
    "evaluate_gold_set",
    "evidence_pack",
    "load_jsonl",
    "load_policy_document",
    "policy_diff",
    "regression_gate",
    "validate_record",
    "write_jsonl",
]
