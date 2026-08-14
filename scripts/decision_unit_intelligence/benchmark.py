"""Funnel and replay metrics. Denominator is always explicit."""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.decision_unit_intelligence.models import AccountInvestigation, AccountTerminal
from scripts.decision_unit_intelligence.reachability import is_actionable_route
from scripts.decision_unit_intelligence.repository import account_hash

ACTION_MODES = (
    "HUMAN_REVIEW_EMAIL",
    "MANUAL_CALL",
    "MANUAL_ROUTED_CALL",
    "MANUAL_WHATSAPP",
    "MANUAL_PROFESSIONAL_SOCIAL",
    "ROLE_EMAIL",
    "CONTACT_FORM",
    "GENERIC_EMAIL_LAST_RESORT",
    "NEEDS_ENRICHMENT",
    "BLOCKED",
    "NO_ACTIONABLE_ROUTE",
)

CLASSES = (
    "R1_DIRECT",
    "R2_HIGH_CONFIDENCE_DIRECT",
    "R3_ROUTED_TO_NAMED_PERSON",
    "R4_ROLE_ROUTE",
    "R5_CORPORATE_ONLY",
    "R0_NO_ACTIONABLE_ROUTE",
    "BLOCKED",
)


def _best_class(account: AccountInvestigation) -> str:
    from scripts.decision_unit_intelligence.reachability import route_rank

    actionable = [r for r in account.routes if is_actionable_route(r)]
    if account.terminal == AccountTerminal.BLOCKED and not actionable:
        return "BLOCKED"
    if not actionable:
        return "R0_NO_ACTIONABLE_ROUTE"
    return max(actionable, key=route_rank).reachability_class.value


def funnel(accounts: list[AccountInvestigation]) -> dict[str, Any]:
    n = len(accounts)
    investigated = [
        a
        for a in accounts
        if a.terminal != AccountTerminal.BLOCKED or a.ledger.stop_reason
    ]
    denom = [
        a
        for a in accounts
        if a.terminal != AccountTerminal.BLOCKED
    ]
    du = sum(1 for a in denom if a.candidates)
    named = sum(1 for a in denom if any(c.person_name for c in a.candidates))
    role = sum(1 for a in denom if any(c.observed_roles for c in a.candidates))
    reachable = sum(1 for a in denom if any(is_actionable_route(r) for r in a.routes))
    classes = Counter(_best_class(a) for a in accounts)
    actions = Counter(
        (a.recommendation.action_mode.value if a.recommendation else "NEEDS_ENRICHMENT")
        for a in accounts
    )
    blocked = sum(1 for a in accounts if a.terminal == AccountTerminal.BLOCKED)
    exhausted = sum(1 for a in accounts if a.terminal == AccountTerminal.EXHAUSTED)
    rate = (reachable / len(denom)) if denom else None
    return {
        "accounts": n,
        "denominator_investigated_with_budget": len(denom),
        "blocked_excluded_from_rate": blocked,
        "exhausted": exhausted,
        "decision_unit_identified": du,
        "named_person_found": named,
        "relevant_role_found": role,
        "decision_unit_reachability_rate": rate,
        "classes": {k: classes.get(k, 0) for k in CLASSES},
        "action_modes": {k: actions.get(k, 0) for k in ACTION_MODES},
        "named_person_coverage": (named / len(denom)) if denom else None,
        "relevant_role_coverage": (role / len(denom)) if denom else None,
        "direct_route_coverage": (classes.get("R1_DIRECT", 0) / len(denom)) if denom else None,
        "routed_to_named_person_coverage": (classes.get("R3_ROUTED_TO_NAMED_PERSON", 0) / len(denom)) if denom else None,
        "role_route_coverage": (classes.get("R4_ROLE_ROUTE", 0) / len(denom)) if denom else None,
        "generic_only_rate": (classes.get("R5_CORPORATE_ONLY", 0) / len(denom)) if denom else None,
        "no_actionable_rate": (classes.get("R0_NO_ACTIONABLE_ROUTE", 0) / len(denom)) if denom else None,
        "blocked_rate": (blocked / n) if n else None,
        "investigated": len(investigated),
        "truth": "BLOCKED is not R0. UNKNOWN is not zero. Rate uses non-blocked denominator.",
    }


def replay_report(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> dict[str, Any]:
    h1 = {a["cnpj"]: account_hash(a) for a in first}
    h2 = {a["cnpj"]: account_hash(a) for a in second}
    keys = sorted(set(h1) | set(h2))
    mismatches = [k for k in keys if h1.get(k) != h2.get(k)]
    return {
        "accounts": len(keys),
        "matches": len(keys) - len(mismatches),
        "mismatches": mismatches,
        "deterministic": not mismatches,
    }
