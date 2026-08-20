"""Versioned public-read-bid-readiness/1.0 types and constants."""

from __future__ import annotations

from typing import Any, Literal

SCHEMA_VERSION = "public-read-bid-readiness/1.0"
PRODUCER_VERSION = "public-read-bid-readiness-producer/1.0"
POLICY_VERSION = "public-read-bid-readiness-policy/1.0"
CONSUMER_ISSUE = "web-cfg#155"

OverallState = Literal["READY_FOR_HUMAN_REVIEW", "HOLD_FOR_DATA", "REJECT"]
FindingState = Literal["FACT", "RISK", "UNKNOWN"]
SourceAccess = Literal["private_local", "redacted_fixture"]

OVERALL_STATES: frozenset[str] = frozenset({"READY_FOR_HUMAN_REVIEW", "HOLD_FOR_DATA", "REJECT"})
FINDING_STATES: frozenset[str] = frozenset({"FACT", "RISK", "UNKNOWN"})
SOURCE_ACCESS_VALUES: frozenset[str] = frozenset({"private_local", "redacted_fixture"})

MODULES_REUSED: tuple[str, ...] = (
    "edital_case",
    "budget_audit",
    "technical_acervo",
    "bid_readiness",
)

DEFAULT_LIMITATIONS: tuple[str, ...] = (
    "Operational coverage envelope only. Not a legal opinion.",
    "Human review is mandatory before any bid decision.",
    "Absence of a document is not a silent eligibility denial.",
    "RISK is a technical condition for human review, not illegality.",
    "No publication, index, or commercial GO is authorized by this producer.",
)

DEFAULT_PROHIBITED_CLAIMS: tuple[str, ...] = (
    "eligibility_conclusion",
    "inexequibility_decision",
    "illegality_label",
    "unscoped_bdi_correctness",
    "win_probability",
    "legal_opinion",
    "autonomous_participate_or_impugn",
    "completeness_without_denominator",
)

INTERPRETIVE_LIMIT = "Observation bound to the cited locator and method. Not a legal conclusion."

ENVELOPE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "query_id",
    "generated_at",
    "as_of",
    "expires_at",
    "input_manifest",
    "engine_versions",
    "policy_version",
    "source_access",
    "overall_state",
    "human_review_required",
    "not_legal_conclusion",
    "publication_authorization",
    "index_authorization",
    "content_hash",
    "limitations",
    "prohibited_claims",
    "findings",
    "summary",
    "reason_codes",
    "producer_version",
)

FINDING_FIELDS: tuple[str, ...] = (
    "finding_id",
    "requirement_id",
    "category",
    "state",
    "statement",
    "source_document_id",
    "locator",
    "evidence_hash",
    "evidence_ref",
    "confidence",
    "coverage",
    "reason_codes",
    "contradiction_links",
    "interpretive_limit",
    "human_review_required",
)

SUMMARY_FIELDS: tuple[str, ...] = (
    "covered_items",
    "missing_items",
    "conflicts",
    "unevaluated",
    "blockers",
    "human_next_steps",
    "observable_review",
)

HOLD_REASON_CODES: frozenset[str] = frozenset(
    {
        "missing_edital",
        "missing_planilha",
        "missing_acervo",
        "missing_documents",
        "engine_unavailable",
        "unreadable_pdf",
        "incomplete_document",
        "insufficient_coverage",
        "contradictory_requirement",
        "locator_missing",
        "sensitive_acervo",
    }
)

REJECT_REASON_CODES: frozenset[str] = frozenset(
    {
        "path_traversal",
        "zip_bomb",
        "oversized",
        "disallowed_type",
        "malware_like",
        "symlink_blocked",
        "csv_injection",
        "unauthorized_manifest",
        "manifest_path_escape",
    }
)


def default_policy() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "human_review_required": True,
        "publication_authorization": False,
        "index_authorization": False,
        "allow_llm": False,
        "deterministic": True,
    }
