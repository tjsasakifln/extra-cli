"""Operational EMAIL_VALIDATED promotion policy (versioned, fail-closed).

A contact becomes EMAIL_VALIDATED only when every condition below holds.
Score ≥ X never promotes. MX/DNS never proves identity. INFERRED never
becomes OBSERVED.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.email_validated.schema import (
    AdjudicationRecord,
    PromotionDecision,
)

POLICY_ID = "dui.email-validated-promotion"
POLICY_VERSION = "dui.email-validated-promotion.v1"
POLICY_SCHEMA_ID = "confenge.email-validated-promotion.v1"

PROFESSIONAL_PUBLIC_SOURCES = frozenset(
    {
        "company_website",
        "official_document",
        "administrative_process",
        "public_gazette",
        "pncp_document",
    }
)

# v1 ships with an empty exception list. A later version may add named
# exceptions; each must be explicit in the policy document.
APPROVED_EXCEPTIONS: frozenset[str] = frozenset()

PREDICTED_EMAIL_VALIDATED = "EMAIL_VALIDATED"
PREDICTED_NOT_PROMOTED = "NOT_PROMOTED"


def decide_promotion(record: AdjudicationRecord | dict[str, Any]) -> PromotionDecision:
    """Pure promotion decision. Does not read human_verdict."""
    rec = record if isinstance(record, AdjudicationRecord) else AdjudicationRecord.from_dict(record)
    reasons: list[str] = []
    epistemic = rec.epistemic
    if epistemic == "INFERRED":
        reasons.append("INFERRED_NOT_OBSERVED")
        reasons.append("INFERRED_CANNOT_BECOME_OBSERVED")
    if not rec.person_name:
        reasons.append("MISSING_PERSON")
    if not rec.email:
        reasons.append("MISSING_EMAIL")
    mailbox = rec.mailbox_kind()
    if mailbox in {"GENERIC", "ROLE"}:
        reasons.append("GENERIC_OR_ROLE_MAILBOX")
    if mailbox == "THIRD_PARTY_DOMAIN":
        reasons.append("THIRD_PARTY_DOMAIN")
    if rec.identity_association != "ASSOCIATED":
        reasons.append("IDENTITY_NOT_ASSOCIATED")
    if rec.identity_association == "AMBIGUOUS":
        reasons.append("IDENTITY_AMBIGUOUS")
    if rec.affiliation != "DEFENSIBLE":
        reasons.append("AFFILIATION_NOT_DEFENSIBLE")
    if rec.affiliation in {"HOLDING", "THIRD_PARTY"}:
        reasons.append("HOLDING_OR_THIRD_PARTY_AFFILIATION")
    if rec.third_party_echo:
        reasons.append("THIRD_PARTY_ECHO")
    source_ok = rec.source in PROFESSIONAL_PUBLIC_SOURCES
    exception_ok = bool(rec.approved_exception) and rec.approved_exception in APPROVED_EXCEPTIONS
    if rec.approved_exception and rec.approved_exception not in APPROVED_EXCEPTIONS:
        reasons.append("APPROVED_EXCEPTION_NOT_IN_POLICY")
    if not source_ok and not exception_ok:
        reasons.append("SOURCE_NOT_PROFESSIONAL_PUBLIC")
    if not rec.has_provenance():
        reasons.append("MISSING_PROVENANCE")
    if not rec.has_source_date():
        reasons.append("MISSING_SOURCE_DATE")
    if rec.freshness == "STALE":
        reasons.append("STALE")
    if rec.freshness == "UNKNOWN":
        reasons.append("FRESHNESS_UNKNOWN")
    if rec.suppression != "NONE":
        reasons.append("SUPPRESSED")
    if rec.technical_status == "HARD_FAIL":
        reasons.append("TECHNICAL_HARD_FAIL")
    # MX/DNS and numeric score are never identity proof and never a
    # positive promotion signal. They block only incomplete packs.
    incomplete_for_identity = bool(
        reasons
        or rec.identity_association != "ASSOCIATED"
        or rec.epistemic != "OBSERVED"
        or not rec.person_name
        or not rec.email
        or mailbox != "NOMINAL"
    )
    if rec.technical_status == "MX_PRESENT":
        if incomplete_for_identity:
            reasons.append("MX_DNS_NOT_IDENTITY")
        else:
            reasons.append("MX_DNS_IGNORED_NOT_IDENTITY")
    if rec.score is not None and incomplete_for_identity:
        reasons.append("SCORE_ALONE_INSUFFICIENT")
    elif rec.score is not None:
        reasons.append("SCORE_IGNORED_NOT_A_PROMOTION_SIGNAL")

    if epistemic == "INFERRED":
        epistemic = "INFERRED"
    informational = {
        "SCORE_IGNORED_NOT_A_PROMOTION_SIGNAL",
        "MX_DNS_IGNORED_NOT_IDENTITY",
    }
    blockers = [code for code in reasons if code not in informational]
    promote = not blockers and epistemic == "OBSERVED"

    predicted = PREDICTED_EMAIL_VALIDATED if promote else PREDICTED_NOT_PROMOTED
    if promote:
        reasons.append("POLICY_PASS")
    return PromotionDecision(
        promote=promote,
        predicted_class=predicted,
        policy_version=POLICY_VERSION,
        epistemic=epistemic,
        reasons=tuple(dict.fromkeys(reasons)),
        case_id=rec.case_id,
    )


def policy_document() -> dict[str, Any]:
    return {
        "schema_id": POLICY_SCHEMA_ID,
        "policy_id": POLICY_ID,
        "version": POLICY_VERSION,
        "auto_send": False,
        "primary_metric": "precision_email_validated",
        "coverage_is_secondary": True,
        "operational_email_validated": {
            "requires": [
                "real_known_person",
                "defensible_person_company_affiliation",
                "email_observed_on_professional_public_source_or_approved_exception",
                "provenance_present",
                "freshness_sufficient",
                "suppression_clear",
                "no_technical_hard_fail",
                "identity_explicitly_associated",
                "epistemic_observed",
                "not_generic_or_role_mailbox",
            ],
            "never_sufficient_alone": [
                "score_gte_x",
                "mx_or_dns",
                "inferred_pattern",
                "local_part_name_match",
            ],
            "hard_bans": [
                "INFERRED_never_becomes_OBSERVED",
                "MX_DNS_never_proves_identity",
                "score_alone_never_promotes",
            ],
        },
        "professional_public_sources": sorted(PROFESSIONAL_PUBLIC_SOURCES),
        "approved_exceptions": sorted(APPROVED_EXCEPTIONS),
        "freshness": {
            "promotable": ["FRESH", "AGING"],
            "blocks": ["STALE", "UNKNOWN"],
            "stale_after_months": 18,
            "aging_after_months": 12,
        },
        "stop_the_line": ["WRONG_PERSON", "WRONG_COMPANY"],
    }


def load_policy_document(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return policy_document()
    return json.loads(Path(path).read_text(encoding="utf-8"))


def policy_fingerprint(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def policy_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_version = str(left.get("version") or left.get("policy_version") or "")
    right_version = str(right.get("version") or right.get("policy_version") or "")
    left_hash = policy_fingerprint(left)
    right_hash = policy_fingerprint(right)
    left_keys = set(left)
    right_keys = set(right)
    changed = sorted(key for key in left_keys & right_keys if left.get(key) != right.get(key))
    return {
        "left_version": left_version,
        "right_version": right_version,
        "left_sha256": left_hash,
        "right_sha256": right_hash,
        "version_changed": left_version != right_version,
        "content_changed": left_hash != right_hash,
        "added_keys": sorted(right_keys - left_keys),
        "removed_keys": sorted(left_keys - right_keys),
        "changed_keys": changed,
        "noop": left_hash == right_hash,
    }
