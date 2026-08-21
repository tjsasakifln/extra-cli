"""Funnel and replay metrics. Denominator is always explicit."""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.decision_unit_intelligence.controlled_email import (
    EmailRouteClass,
    classify_account_email_routes,
)
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
    preferred_initial_accounts = 0
    double_preferred = 0
    route_class_counts: Counter[str] = Counter()
    account_class_counts: Counter[str] = Counter()
    official_domain_proven = 0
    any_public_email_observed = 0
    exclusion_reasons: Counter[str] = Counter()
    pages = 0
    requests = 0
    no_domain = 0
    no_email = 0
    inferred_only = 0
    blocked_mailbox = 0
    stale = 0
    suppression = 0
    duplicates = 0
    for account in denom:
        ranking = classify_account_email_routes(account)
        preferred_flags = [item for item in ranking.classified_routes if item.preferred_initial]
        if ranking.preferred_initial_route is not None:
            preferred_initial_accounts += 1
        if len(preferred_flags) > 1:
            double_preferred += 1
        if any(item.controlled_email_eligible for item in ranking.classified_routes):
            classified_email_reachable += 1
        seen_classes: set[str] = set()
        observed_any = False
        inferred_seen = False
        observed_non_inferred = False
        mailboxes: set[str] = set()
        for item in ranking.classified_routes:
            route_class_counts[item.route_class.value] += 1
            seen_classes.add(item.route_class.value)
            if item.mailbox in mailboxes:
                duplicates += 1
            mailboxes.add(item.mailbox)
            if item.epistemic_class == "INFERRED" or item.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY:
                inferred_seen = True
            else:
                observed_non_inferred = True
                observed_any = True
            if item.freshness == "STALE":
                stale += 1
            if item.suppression_state not in {"NONE", "", None}:
                suppression += 1
            if not item.controlled_email_eligible:
                for code in item.reason_codes:
                    if code.startswith("mailbox_purpose") or code in {
                        "stale",
                        "opt_out",
                        "hard_bounce",
                        "dnc",
                        "inferred_or_catch_all",
                        "unassociated_freemail",
                        "impossible_domain",
                        "third_party_professional_domain",
                        "risky_excluded_from_default_pilot",
                    }:
                        exclusion_reasons[code] += 1
                if any("mailbox_purpose" in code or "human_recipient" in code for code in item.reason_codes):
                    blocked_mailbox += 1
        for klass in seen_classes:
            account_class_counts[klass] += 1
        if observed_any:
            any_public_email_observed += 1
        if inferred_seen and not observed_non_inferred:
            inferred_only += 1
        if not ranking.classified_routes:
            no_email += 1
        domain = (account.extra or {}).get("domain_resolution") or {}
        if isinstance(domain, dict) and domain.get("canonical_domain"):
            official_domain_proven += 1
        elif account.legal_name and any("@" in str(r.channel_value or "") for r in account.routes):
            official_domain_proven += 0
        else:
            if not domain.get("canonical_domain") if isinstance(domain, dict) else True:
                no_domain += 1
        pages += int((account.ledger.attempts and sum(a.documents_checked for a in account.ledger.attempts)) or 0)
        requests += int(account.ledger.provider_attempts or 0)
        if account.terminal.value == "EXHAUSTED":
            exclusion_reasons["source_exhaustion"] += 1
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
        "official_domain_proven": official_domain_proven,
        "any_public_email_observed": any_public_email_observed,
        "DIRECT_PERSON": account_class_counts.get(EmailRouteClass.DIRECT_PERSON.value, 0),
        "ROLE_OR_DEPARTMENT": account_class_counts.get(EmailRouteClass.ROLE_OR_DEPARTMENT.value, 0),
        "GENERIC_COMPANY": account_class_counts.get(EmailRouteClass.GENERIC_COMPANY.value, 0),
        "PUBLIC_COMPANY_FREEMAIL": account_class_counts.get(EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value, 0),
        "PROBABILISTIC_OR_RISKY": account_class_counts.get(EmailRouteClass.PROBABILISTIC_OR_RISKY.value, 0),
        "controlled_email_eligible": classified_email_reachable,
        "preferred_initial_route": preferred_initial_accounts,
        "double_preferred_accounts": double_preferred,
        "no_domain": no_domain,
        "no_email": no_email,
        "generic_found": account_class_counts.get(EmailRouteClass.GENERIC_COMPANY.value, 0),
        "role_found": account_class_counts.get(EmailRouteClass.ROLE_OR_DEPARTMENT.value, 0),
        "freemail_found": account_class_counts.get(EmailRouteClass.PUBLIC_COMPANY_FREEMAIL.value, 0),
        "named_found": account_class_counts.get(EmailRouteClass.DIRECT_PERSON.value, 0),
        "inferred_only": inferred_only,
        "blocked_mailbox": blocked_mailbox,
        "stale": stale,
        "suppression": suppression,
        "duplicates": duplicates,
        "source_exhaustion": exclusion_reasons.get("source_exhaustion", 0),
        "exclusion_reason_codes": dict(exclusion_reasons),
        "pages": pages,
        "requests": requests,
        "auto_send": False,
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
