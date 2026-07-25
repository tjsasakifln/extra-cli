"""Bid Submission Readiness — operational dossier capability (file-only, no DB/VPS)."""

__version__ = "0.1.0"
CAMPAIGN_ID = "BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01"

# Dual readiness enums (closed sets — never invent portal-ready synonyms)
SYSTEM_STATUSES = frozenset({"SYSTEM_PASS", "SYSTEM_BLOCKED", "SYSTEM_FAIL"})
PACKAGE_STATUSES = frozenset(
    {
        "READY_FOR_HUMAN_REVIEW",
        "NOT_READY",
        "BLOCKED_BY_MISSING_DOCUMENT",
        "BLOCKED_BY_EXPIRED_DOCUMENT",
        "BLOCKED_BY_INCONSISTENCY",
        "BLOCKED_BY_TECHNICAL_QUALIFICATION",
        "BLOCKED_BY_HUMAN_DECISION",
    }
)

FORBIDDEN_SUCCESS_LABELS = frozenset(
    {
        "READY_TO_SUBMIT",
        "HABILITADA",
        "PROPOSTA APROVADA",
        "GARANTIA ACEITA",
    }
)
