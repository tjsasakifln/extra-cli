"""Investigation state machine for process-first enrichment.

NO_CONTACT_FOUND is only allowed after the applicable public cascade was
exhausted or an explicit blocker was recorded — never after site/web-only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class InvestigationState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    CONTRACTS_RESOLVED = "CONTRACTS_RESOLVED"
    PNCP_CONTRACT_DOCS_FETCHED = "PNCP_CONTRACT_DOCS_FETCHED"
    PROCUREMENT_RESOLVED = "PROCUREMENT_RESOLVED"
    PROCUREMENT_DOCS_FETCHED = "PROCUREMENT_DOCS_FETCHED"
    PROCESS_NUMBER_RESOLVED = "PROCESS_NUMBER_RESOLVED"
    PROCESS_PORTAL_RESOLVED = "PROCESS_PORTAL_RESOLVED"
    PROCESS_INDEX_FETCHED = "PROCESS_INDEX_FETCHED"
    HIGH_VALUE_DOCS_FETCHED = "HIGH_VALUE_DOCS_FETCHED"
    DOCS_PARSED = "DOCS_PARSED"
    CONTACTS_EXTRACTED = "CONTACTS_EXTRACTED"
    CONTACTS_RESOLVED = "CONTACTS_RESOLVED"
    CONTACTS_VERIFIED = "CONTACTS_VERIFIED"
    COMPLETE = "COMPLETE"


class TerminalState(StrEnum):
    """Account-level terminal investigation outcomes (mutually exclusive intent)."""

    NO_CONTACT_FOUND = "NO_CONTACT_FOUND"
    PROCESS_NOT_TRACED = "PROCESS_NOT_TRACED"
    PROCESS_FOUND_NOT_FETCHED = "PROCESS_FOUND_NOT_FETCHED"
    DOCUMENTS_NOT_FETCHED = "DOCUMENTS_NOT_FETCHED"
    DOCUMENTS_FETCHED_NOT_PARSED = "DOCUMENTS_FETCHED_NOT_PARSED"
    DOCUMENTS_PARSED_NO_CONTACT = "DOCUMENTS_PARSED_NO_CONTACT"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    SOURCE_REQUIRES_HUMAN_ACCESS = "SOURCE_REQUIRES_HUMAN_ACCESS"
    CONTACT_FOUND_UNVERIFIED = "CONTACT_FOUND_UNVERIFIED"
    CONTACT_FOUND_VERIFIED = "CONTACT_FOUND_VERIFIED"
    EMAIL_SEND_READY = "EMAIL_SEND_READY"
    REFERRAL_ROUTE_AVAILABLE = "REFERRAL_ROUTE_AVAILABLE"
    # Exceptional terminals
    SOURCE_NOT_PUBLIC = "SOURCE_NOT_PUBLIC"
    CAPTCHA_BLOCKED = "CAPTCHA_BLOCKED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    PROCESS_NOT_FOUND = "PROCESS_NOT_FOUND"
    DOCUMENTS_NOT_AVAILABLE = "DOCUMENTS_NOT_AVAILABLE"
    PARSED_NO_CONTACT = "PARSED_NO_CONTACT"


# Progressive order for monotonic advancement checks
_PROGRESS: list[InvestigationState] = list(InvestigationState)


def advance(current: InvestigationState, target: InvestigationState) -> InvestigationState:
    """Move forward only; never regress."""
    if _PROGRESS.index(target) >= _PROGRESS.index(current):
        return target
    return current


def can_declare_no_contact(
    *,
    state: InvestigationState | str,
    terminal: TerminalState | str | None = None,
    process_path_applicable: bool = True,
    process_path_attempted: bool = False,
    process_path_blocked: bool = False,
    site_web_only: bool = False,
) -> bool:
    """Return True only when NO_CONTACT_FOUND is epistemically honest.

    Hard rule: site/web-only failure never qualifies while a process path
    remains applicable and unattempted.
    """
    st = InvestigationState(state) if not isinstance(state, InvestigationState) else state
    if site_web_only and process_path_applicable and not process_path_attempted:
        return False
    if process_path_applicable and not process_path_attempted and not process_path_blocked:
        return False
    # Exhaustion: docs parsed with no commercial contact, or explicit blocker
    exhausted = st in {
        InvestigationState.DOCS_PARSED,
        InvestigationState.CONTACTS_EXTRACTED,
        InvestigationState.CONTACTS_RESOLVED,
        InvestigationState.CONTACTS_VERIFIED,
        InvestigationState.COMPLETE,
    }
    if process_path_blocked:
        return True
    if terminal in {
        TerminalState.SOURCE_BLOCKED,
        TerminalState.CAPTCHA_BLOCKED,
        TerminalState.AUTH_REQUIRED,
        TerminalState.SOURCE_REQUIRES_HUMAN_ACCESS,
        TerminalState.SOURCE_NOT_PUBLIC,
        TerminalState.DOCUMENTS_NOT_AVAILABLE,
        TerminalState.PROCESS_NOT_FOUND,
    }:
        return True
    return exhausted


def derive_terminal(
    *,
    state: InvestigationState | str,
    has_enrollable_email: bool,
    has_verified_email: bool,
    has_referral_route: bool,
    has_unverified_contact: bool,
    process_path_applicable: bool,
    process_path_attempted: bool,
    process_number_found: bool,
    portal_resolved: bool,
    docs_fetched: bool,
    docs_parsed: bool,
    blockers: list[str] | None = None,
) -> TerminalState:
    """Map cascade progress + findings to a single terminal outcome."""
    st = InvestigationState(state) if not isinstance(state, InvestigationState) else state
    blockers = blockers or []

    if has_enrollable_email:
        return TerminalState.EMAIL_SEND_READY
    if has_verified_email:
        return TerminalState.CONTACT_FOUND_VERIFIED
    if has_referral_route:
        return TerminalState.REFERRAL_ROUTE_AVAILABLE
    if has_unverified_contact:
        return TerminalState.CONTACT_FOUND_UNVERIFIED

    # Document-path outcomes dominate when that path was actually exercised
    # (e.g. PNCP docs parsed even if SEI captcha also fired).
    if docs_parsed:
        return TerminalState.DOCUMENTS_PARSED_NO_CONTACT
    if docs_fetched and not docs_parsed:
        return TerminalState.DOCUMENTS_FETCHED_NOT_PARSED
    if portal_resolved and not docs_fetched:
        # Prefer explicit source blockers only when no doc body path completed
        blocker_join = " ".join(blockers).upper()
        if "CAPTCHA" in blocker_join and not docs_fetched:
            # Portal known but captcha blocks the *only* remaining doc source
            # Keep DOCUMENTS_NOT_FETCHED if PNCP index existed without body
            pass
        return TerminalState.DOCUMENTS_NOT_FETCHED
    if process_number_found and not portal_resolved:
        return TerminalState.PROCESS_FOUND_NOT_FETCHED
    if process_path_attempted and not process_number_found:
        return TerminalState.PROCESS_NOT_FOUND
    if process_path_applicable and not process_path_attempted:
        return TerminalState.PROCESS_NOT_TRACED

    blocker_join = " ".join(blockers).upper()
    if "CAPTCHA" in blocker_join:
        return TerminalState.CAPTCHA_BLOCKED
    if "AUTH" in blocker_join:
        return TerminalState.AUTH_REQUIRED
    if any(b in blocker_join for b in ("BLOCKED", "RATE_LIMIT", "403", "429")):
        return TerminalState.SOURCE_BLOCKED
    if "NOT_PUBLIC" in blocker_join or "PRIVATE" in blocker_join:
        return TerminalState.SOURCE_NOT_PUBLIC
    if "HUMAN" in blocker_join:
        return TerminalState.SOURCE_REQUIRES_HUMAN_ACCESS

    if st == InvestigationState.NOT_STARTED:
        return TerminalState.PROCESS_NOT_TRACED
    return TerminalState.NO_CONTACT_FOUND


def funnel_snapshot(account_results: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate funnel counters for observability."""
    keys = [
        "accounts_total",
        "accounts_contract_resolved",
        "accounts_process_number_resolved",
        "accounts_process_portal_resolved",
        "accounts_documents_fetched",
        "accounts_company_authored_docs_found",
        "accounts_with_any_email",
        "accounts_with_verified_email",
        "accounts_with_enrollable_email",
        "accounts_with_named_contact",
        "accounts_with_relevant_role",
        "accounts_with_referral_route",
        "accounts_process_exhausted_no_contact",
    ]
    out = {k: 0 for k in keys}
    out["accounts_total"] = len(account_results)
    for r in account_results:
        if r.get("contracts_resolved"):
            out["accounts_contract_resolved"] += 1
        if r.get("process_number_resolved"):
            out["accounts_process_number_resolved"] += 1
        if r.get("process_portal_resolved"):
            out["accounts_process_portal_resolved"] += 1
        if r.get("documents_fetched"):
            out["accounts_documents_fetched"] += 1
        if r.get("company_authored_docs_found"):
            out["accounts_company_authored_docs_found"] += 1
        if r.get("any_email"):
            out["accounts_with_any_email"] += 1
        if r.get("verified_email"):
            out["accounts_with_verified_email"] += 1
        if r.get("enrollable_email"):
            out["accounts_with_enrollable_email"] += 1
        if r.get("named_contact"):
            out["accounts_with_named_contact"] += 1
        if r.get("relevant_role"):
            out["accounts_with_relevant_role"] += 1
        if r.get("referral_route"):
            out["accounts_with_referral_route"] += 1
        term = r.get("terminal_state")
        if term in {
            TerminalState.NO_CONTACT_FOUND.value,
            TerminalState.DOCUMENTS_PARSED_NO_CONTACT.value,
            TerminalState.PARSED_NO_CONTACT.value,
        }:
            out["accounts_process_exhausted_no_contact"] += 1
    return out
