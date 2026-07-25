"""Hybrid sector discovery: retrieval → classify → LLM arbitrate → commercial decision.

Stages (never mixed):
  raw_universe → hybrid_retrieval → ranking_fusion → deterministic_classification
  → llm_arbitration → decision_policy → human_review → evaluation

No stage may silently discard a record.
"""
from __future__ import annotations

PIPELINE_VERSION = "hybrid-sector-recall-llm-arbiter/1.0.0"
RULE_STAMP = "extra-sector-classifier/2.2.0+selective"
PROMPT_VERSION = "sector-arbiter-v1"
SCHEMA_VERSION = "SectorLLMDecision/1.0"

ALLOWED_TERMINAL_STATES = frozenset(
    {
        "BLOCKED_INSUFFICIENT_RECALL",
        "BLOCKED_INSUFFICIENT_STATISTICAL_POWER",
        "BLOCKED_REVIEW_CAPACITY",
        "BLOCKED_LLM_OPERATIONAL_VALIDATION",
        "READY_FOR_RECALL_ASSURANCE_REVIEW",
    }
)

FORBIDDEN_CLAIMS = frozenset(
    {
        "PROJECT_DONE",
        "100% NO FALSE NEGATIVES",
        "FULLY GUARANTEED",
        "ACCEPTED",
        "MERGED",
    }
)

__all__ = [
    "PIPELINE_VERSION",
    "RULE_STAMP",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "ALLOWED_TERMINAL_STATES",
    "FORBIDDEN_CLAIMS",
]
