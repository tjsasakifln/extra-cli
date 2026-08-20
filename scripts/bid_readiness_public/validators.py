"""Fail-closed envelope/finding validators. Pure functions, no I/O."""

from __future__ import annotations

from typing import Any

from scripts.bid_readiness_public.forbidden import scan_forbidden_claims, scan_payload
from scripts.bid_readiness_public.models import (
    ENVELOPE_FIELDS,
    FINDING_FIELDS,
    FINDING_STATES,
    OVERALL_STATES,
    SCHEMA_VERSION,
    SOURCE_ACCESS_VALUES,
    SUMMARY_FIELDS,
)


class EnvelopeValidationError(ValueError):
    """Raised when a finding or envelope violates the 1.0 contract."""


def locator_present(locator: Any) -> bool:
    if not isinstance(locator, dict):
        return False
    for key in ("page", "section", "cell", "sheet", "paragraph"):
        value = locator.get(key)
        if value is not None and value != "" and value != []:
            return True
    return False


def validate_finding(finding: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in FINDING_FIELDS:
        if field not in finding:
            errors.append(f"missing:{field}")
    state = finding.get("state")
    if state not in FINDING_STATES:
        errors.append("state")
    if state == "FACT":
        if not finding.get("evidence_hash"):
            errors.append("fact_without_evidence_hash")
        if not locator_present(finding.get("locator")):
            errors.append("fact_without_locator")
    if state == "RISK":
        method = finding.get("method") or finding.get("rule")
        if not method:
            errors.append("risk_without_method")
        if not finding.get("evidence_hash") and not finding.get("evidence_ref"):
            errors.append("risk_without_evidence")
    statement = str(finding.get("statement") or "")
    errors.extend(f"forbidden_claim:{hit}" for hit in scan_forbidden_claims(statement))
    if finding.get("human_review_required") is not True and state in {"RISK", "UNKNOWN"}:
        errors.append("human_review_required")
    return errors


def refuse_finding(finding: dict[str, Any]) -> None:
    errors = validate_finding(finding)
    if errors:
        raise EnvelopeValidationError(";".join(errors))


def validate_summary(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in SUMMARY_FIELDS:
        if field not in summary:
            errors.append(f"summary.missing:{field}")
    review = summary.get("observable_review") or {}
    if "win_estimate" in review or "chance" in review:
        errors.append("summary.win_estimate")
    return errors


def validate_envelope(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ENVELOPE_FIELDS:
        if field not in payload:
            errors.append(f"missing:{field}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version")
    if payload.get("overall_state") not in OVERALL_STATES:
        errors.append("overall_state")
    if payload.get("human_review_required") is not True:
        errors.append("human_review_required")
    if payload.get("not_legal_conclusion") is not True:
        errors.append("not_legal_conclusion")
    if payload.get("publication_authorization") is not False:
        errors.append("publication_authorization")
    if payload.get("index_authorization") is not False:
        errors.append("index_authorization")
    if payload.get("source_access") not in SOURCE_ACCESS_VALUES:
        errors.append("source_access")
    if not payload.get("content_hash"):
        errors.append("content_hash")
    if not payload.get("input_manifest"):
        errors.append("input_manifest")
    manifest = payload.get("input_manifest") or {}
    for item in manifest.get("inputs") or []:
        if "content" in item or "bytes_content" in item or "text" in item:
            errors.append("input_manifest.contains_content")
        if item.get("present") is False:
            continue
        if not item.get("sha256") or item.get("bytes") is None:
            errors.append("input_manifest.incomplete")
    for index, finding in enumerate(payload.get("findings") or []):
        for err in validate_finding(finding):
            errors.append(f"findings[{index}].{err}")
    errors.extend(validate_summary(payload.get("summary") or {}))
    errors.extend(f"forbidden_claim:{hit}" for hit in scan_payload(payload))
    return errors


def refuse_envelope(payload: dict[str, Any]) -> None:
    errors = validate_envelope(payload)
    if errors:
        raise EnvelopeValidationError(";".join(errors))
