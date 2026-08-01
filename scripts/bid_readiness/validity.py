"""Document validity engine with configurable policies."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from scripts.bid_readiness.extract import field_value, parse_date
from scripts.bid_readiness.models import ValidityStatus


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = parse_date(str(value)) if not isinstance(value, date) else value.isoformat()
    if not s:
        return None
    return date.fromisoformat(str(s)[:10])


def evaluate_validity(
    *,
    metadata: dict[str, Any],
    validity_rule: dict[str, Any] | None,
    reference_date: str,
    session_date: str | None = None,
    contract_signing_date: str | None = None,
    submission_deadline: str | None = None,
    expiring_soon_days: int = 30,
) -> dict[str, Any]:
    """Evaluate validity status for one document against policy/rules."""
    rule = validity_rule or {}
    ref = _as_date(reference_date)
    if ref is None:
        raise ValueError(f"invalid reference_date: {reference_date}")
    _as_date(session_date) or ref
    contract = _as_date(contract_signing_date) or _as_date(rule.get("contract_signing_date"))
    deadline = _as_date(submission_deadline) or _as_date(rule.get("submission_deadline"))

    if rule.get("not_applicable"):
        return _result(ValidityStatus.NOT_APPLICABLE, ref, None, None, "rule.not_applicable")

    if rule.get("no_expiry") or rule.get("validity") == "NO_EXPIRY":
        return _result(ValidityStatus.NO_EXPIRY, ref, None, None, "rule.no_expiry")

    issue_raw = field_value(metadata, "data_emissao")
    expiry_raw = field_value(metadata, "data_validade")
    # rule override for edital-specific validity
    if rule.get("force_valid_until"):
        expiry_raw = rule["force_valid_until"]
    if rule.get("validity_days_from_issue") and issue_raw:
        issue_d = _as_date(issue_raw)
        if issue_d:
            expiry_raw = (issue_d + timedelta(days=int(rule["validity_days_from_issue"]))).isoformat()

    issue_d = _as_date(issue_raw)
    expiry_d = _as_date(expiry_raw)

    if expiry_d is None and issue_d is None and not rule.get("allow_missing_expiry"):
        # distinguish
        if rule.get("requires_expiry", True):
            return _result(
                ValidityStatus.EXPIRY_NOT_FOUND,
                ref,
                issue_d,
                None,
                "expiry not found",
                needs_human=True,
            )
        return _result(ValidityStatus.NO_EXPIRY, ref, issue_d, None, "no expiry required")

    if expiry_d is None:
        return _result(
            ValidityStatus.EXPIRY_NOT_FOUND if issue_d else ValidityStatus.ISSUE_DATE_NOT_FOUND,
            ref,
            issue_d,
            None,
            "dates incomplete",
            needs_human=True,
        )

    if expiry_d < ref:
        return _result(ValidityStatus.EXPIRED, ref, issue_d, expiry_d, "expiry < reference_date")

    if deadline and expiry_d < deadline:
        return _result(
            ValidityStatus.EXPIRES_BEFORE_SUBMISSION,
            ref,
            issue_d,
            expiry_d,
            "expiry < submission_deadline",
        )

    if contract and expiry_d < contract:
        return _result(
            ValidityStatus.EXPIRES_BEFORE_CONTRACT,
            ref,
            issue_d,
            expiry_d,
            "expiry < contract_signing_date",
        )

    soon = ref + timedelta(days=int(rule.get("expiring_soon_days", expiring_soon_days)))
    if expiry_d <= soon:
        return _result(ValidityStatus.EXPIRING_SOON, ref, issue_d, expiry_d, "within expiring window")

    return _result(ValidityStatus.VALID, ref, issue_d, expiry_d, "valid at reference_date")


def _result(
    status: ValidityStatus,
    ref: date,
    issue: date | None,
    expiry: date | None,
    reason: str,
    needs_human: bool = False,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "reference_date": ref.isoformat(),
        "issue_date": issue.isoformat() if issue else None,
        "expiry_date": expiry.isoformat() if expiry else None,
        "reason": reason,
        "needs_human": needs_human or status == ValidityStatus.NEEDS_HUMAN,
    }
