"""Funnel and replay metrics. Denominator is always explicit."""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.decision_unit_intelligence.controlled_email import classify_account_email_routes
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    AccountTerminal,
    FirstClassRouteKind,
    FirstClassRouteLabel,
    ReachabilityClass,
)
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
    investigated = [a for a in accounts if a.terminal != AccountTerminal.BLOCKED or a.ledger.stop_reason]
    denom = [a for a in accounts if a.terminal != AccountTerminal.BLOCKED]
    du = sum(1 for a in denom if a.candidates)
    named = sum(1 for a in denom if any(c.person_name for c in a.candidates))
    role = sum(1 for a in denom if any(c.observed_roles for c in a.candidates))
    reachable = sum(1 for a in denom if any(is_actionable_route(r) for r in a.routes))
    classified_email_reachable = 0
    route_class_counts: Counter[str] = Counter()
    for account in denom:
        ranking = classify_account_email_routes(account)
        if any(item.controlled_email_eligible for item in ranking.classified_routes):
            classified_email_reachable += 1
        for item in ranking.classified_routes:
            route_class_counts[item.route_class.value] += 1
    classes = Counter(_best_class(a) for a in accounts)
    actions = Counter(
        (a.recommendation.action_mode.value if a.recommendation else "NEEDS_ENRICHMENT") for a in accounts
    )
    blocked = sum(1 for a in accounts if a.terminal == AccountTerminal.BLOCKED)
    exhausted = sum(1 for a in accounts if a.terminal == AccountTerminal.EXHAUSTED)
    rate = (reachable / len(denom)) if denom else None
    routed = sum(
        1
        for a in denom
        if any(
            r.first_class_kind == FirstClassRouteKind.ROUTED_CALL
            or r.reachability_class == ReachabilityClass.R3_ROUTED_TO_NAMED_PERSON
            for r in a.routes
            if is_actionable_route(r)
        )
    )
    whatsapp = sum(
        1 for a in denom if any(r.first_class_label == FirstClassRouteLabel.PUBLIC_WHATSAPP for r in a.routes)
    )
    from scripts.decision_unit_intelligence.reachability import route_rank

    first_labels: Counter[str] = Counter()
    for account in denom:
        actionable_routes = [route for route in account.routes if is_actionable_route(route)]
        if not actionable_routes:
            first_labels[FirstClassRouteLabel.UNKNOWN.value] += 1
        else:
            first_labels[max(actionable_routes, key=route_rank).first_class_label.value] += 1
    unresolved = _unresolved_reasons(denom)
    cost_latency = _cost_latency_per_class(accounts)
    denom_n = len(denom)
    return {
        "accounts": n,
        "denominator": {
            "accounts": n,
            "investigated_non_blocked": denom_n,
            "explicit": True,
            "note": "Rates use non-blocked investigated accounts as denominator.",
        },
        "denominator_investigated_with_budget": denom_n,
        "blocked_excluded_from_rate": blocked,
        "exhausted": exhausted,
        "decision_unit_identified": du,
        "named_person_found": named,
        "relevant_role_found": role,
        "decision_unit_reachability_rate": rate,
        "classified_email_reachable_per_account": (classified_email_reachable / denom_n) if denom_n else None,
        "classified_email_route_classes": dict(route_class_counts),
        "actionable_route_per_account": (reachable / denom_n) if denom_n else None,
        "routed_call_per_account": (routed / denom_n) if denom_n else None,
        "decision_unit_known_per_account": (du / denom_n) if denom_n else None,
        "public_whatsapp_per_account": (whatsapp / denom_n) if denom_n else None,
        "unresolved_reason_distribution": unresolved,
        "cost_latency_per_route_class": cost_latency,
        "first_class_labels": dict(first_labels),
        "classes": {k: classes.get(k, 0) for k in CLASSES},
        "action_modes": {k: actions.get(k, 0) for k in ACTION_MODES},
        "named_person_coverage": (named / denom_n) if denom_n else None,
        "relevant_role_coverage": (role / denom_n) if denom_n else None,
        "direct_route_coverage": (classes.get("R1_DIRECT", 0) / denom_n) if denom_n else None,
        "routed_to_named_person_coverage": (classes.get("R3_ROUTED_TO_NAMED_PERSON", 0) / denom_n) if denom_n else None,
        "role_route_coverage": (classes.get("R4_ROLE_ROUTE", 0) / denom_n) if denom_n else None,
        "generic_only_rate": (classes.get("R5_CORPORATE_ONLY", 0) / denom_n) if denom_n else None,
        "no_actionable_rate": (classes.get("R0_NO_ACTIONABLE_ROUTE", 0) / denom_n) if denom_n else None,
        "blocked_rate": (blocked / n) if n else None,
        "investigated": len(investigated),
        "truth": "BLOCKED is not R0. UNKNOWN is not zero. Rate uses non-blocked denominator.",
    }


def _unresolved_reasons(accounts: list[AccountInvestigation]) -> dict[str, int]:
    reasons: Counter[str] = Counter()
    for account in accounts:
        if any(is_actionable_route(route) for route in account.routes):
            continue
        if not account.candidates:
            reasons["NO_DECISION_UNIT"] += 1
        elif account.terminal == AccountTerminal.DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED:
            reasons["DECISION_UNIT_WITHOUT_ROUTE"] += 1
        else:
            reasons["UNRESOLVED"] += 1
        for code in account.reason_codes:
            reasons[code] += 1
    return dict(reasons)


def _cost_latency_per_class(accounts: list[AccountInvestigation]) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, dict[str, float | int]] = {}
    for account in accounts:
        klass = _best_class(account)
        bucket = buckets.setdefault(klass, {"n": 0, "cost_brl": 0.0, "duration_ms": 0})
        bucket["n"] = int(bucket["n"]) + 1
        bucket["cost_brl"] = float(bucket["cost_brl"]) + float(account.ledger.cost_brl)
        bucket["duration_ms"] = int(bucket["duration_ms"]) + int(account.ledger.duration_ms)
        kinds = {route.first_class_kind.value for route in account.routes} or {
            FirstClassRouteKind.MANUAL_RESEARCH.value
        }
        for kind in kinds:
            kind_bucket = buckets.setdefault(
                f"kind:{kind}",
                {"n": 0, "cost_brl": 0.0, "duration_ms": 0},
            )
            kind_bucket["n"] = int(kind_bucket["n"]) + 1
            kind_bucket["cost_brl"] = float(kind_bucket["cost_brl"]) + float(account.ledger.cost_brl)
            kind_bucket["duration_ms"] = int(kind_bucket["duration_ms"]) + int(account.ledger.duration_ms)
    return buckets


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
