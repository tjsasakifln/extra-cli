"""Real-shaped controlled-email reachability cohort.

Replays stored/fixture observations through the shipped classifier + funnel.
Never sends mail. auto_send stays false.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.benchmark import funnel
from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS
from scripts.decision_unit_intelligence.controlled_email import (
    classify_account_email_routes,
    departmental_hypothesis_mailboxes,
)
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelType,
    EpistemicClass,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SearchLedger,
    SuppressionState,
)

COHORT_SCHEMA = "confenge.controlled_email.cohort_funnel.v1"
AUTO_SEND = False


def _cnpj14(index: int) -> str:
    if index < len(TRACK_A_CNPJS):
        return TRACK_A_CNPJS[index]
    return f"{index + 10000000000000:014d}"


def _route(
    account_id: str,
    mailbox: str,
    *,
    channel: ChannelType,
    relation: RouteRelation,
    reachability: ReachabilityClass,
    action: ActionMode,
    epistemic: EpistemicClass = EpistemicClass.OBSERVED,
    source: str = "company_website",
    extra: dict[str, Any] | None = None,
    suppression: SuppressionState = SuppressionState.NONE,
) -> ReachabilityRoute:
    payload = dict(extra or {})
    return ReachabilityRoute(
        route_id=f"{account_id}:{mailbox}",
        company_entity_id=account_id,
        channel_type=channel,
        reachability_class=reachability,
        action_mode=action,
        channel_value=mailbox,
        route_relation=relation,
        epistemic_class=epistemic,
        source_type=source,
        source_url=f"https://{mailbox.split('@', 1)[-1]}/contato" if "@" in mailbox else None,
        ownership=OwnershipStatus.COMPANY_OWNED
        if source in {"company_website", "site", "official_documents"}
        else OwnershipStatus.UNKNOWN,
        suppression=suppression,
        extra=payload,
    )


def build_real_shaped_cohort(n: int = 120) -> list[AccountInvestigation]:
    """Build ≥100 ICP-shaped accounts. Yield is computed by shipped classify/funnel."""
    if n < 100:
        raise ValueError("cohort must have at least 100 accounts")
    accounts: list[AccountInvestigation] = []
    templates = (
        "role_licitacao",
        "role_comercial",
        "generic_contato",
        "footer_licitacao",
        "named_person",
        "official_gmail",
        "snippet_gmail",
        "rh_blocked",
        "inferred_only",
        "no_email",
        "multi_mailbox",
        "press_blocked",
    )
    for index in range(n):
        cnpj = _cnpj14(index)
        domain = f"empresa{index:03d}.com.br"
        kind = templates[index % len(templates)]
        routes: list[ReachabilityRoute] = []
        extra: dict[str, Any] = {"auto_send": AUTO_SEND}
        if kind != "no_email":
            extra["domain_resolution"] = {"canonical_domain": domain}
        if kind == "role_licitacao":
            routes = [
                _route(
                    cnpj,
                    f"licitacao@{domain}",
                    channel=ChannelType.ROLE_MAILBOX,
                    relation=RouteRelation.ROUTES_TO_ROLE,
                    reachability=ReachabilityClass.R4_ROLE_ROUTE,
                    action=ActionMode.ROLE_EMAIL,
                    extra={"email_discovery_class": "ROLE_MAILBOX", "company_associated": True},
                )
            ]
        elif kind == "role_comercial":
            routes = [
                _route(
                    cnpj,
                    f"comercial@{domain}",
                    channel=ChannelType.ROLE_MAILBOX,
                    relation=RouteRelation.ROUTES_TO_ROLE,
                    reachability=ReachabilityClass.R4_ROLE_ROUTE,
                    action=ActionMode.ROLE_EMAIL,
                    extra={"email_discovery_class": "ROLE_MAILBOX", "company_associated": True},
                )
            ]
        elif kind in {"generic_contato", "footer_licitacao"}:
            local = "licitacao" if kind == "footer_licitacao" else "contato"
            channel = ChannelType.ROLE_MAILBOX if local == "licitacao" else ChannelType.GENERIC_CORPORATE_EMAIL
            routes = [
                _route(
                    cnpj,
                    f"{local}@{domain}",
                    channel=channel,
                    relation=RouteRelation.ACCOUNT_LEVEL_ONLY if local == "contato" else RouteRelation.ROUTES_TO_ROLE,
                    reachability=ReachabilityClass.R5_CORPORATE_ONLY
                    if local == "contato"
                    else ReachabilityClass.R4_ROLE_ROUTE,
                    action=ActionMode.GENERIC_EMAIL_LAST_RESORT if local == "contato" else ActionMode.ROLE_EMAIL,
                    extra={"company_associated": True, "site_association_strength": "company_only"},
                )
            ]
        elif kind == "named_person":
            routes = [
                _route(
                    cnpj,
                    f"ana.souza@{domain}",
                    channel=ChannelType.DIRECT_EMAIL,
                    relation=RouteRelation.PERSON_OWNS_CHANNEL,
                    reachability=ReachabilityClass.R1_DIRECT,
                    action=ActionMode.HUMAN_REVIEW_EMAIL,
                    extra={"identity_explicitly_associated": True, "observed_person_name": "ANA SOUZA"},
                )
            ]
        elif kind == "official_gmail":
            routes = [
                _route(
                    cnpj,
                    f"contato.empresa{index}@gmail.com",
                    channel=ChannelType.GENERIC_CORPORATE_EMAIL,
                    relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
                    reachability=ReachabilityClass.R5_CORPORATE_ONLY,
                    action=ActionMode.GENERIC_EMAIL_LAST_RESORT,
                    extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
                )
            ]
        elif kind == "snippet_gmail":
            routes = [
                _route(
                    cnpj,
                    f"alguem{index}@gmail.com",
                    channel=ChannelType.GENERIC_CORPORATE_EMAIL,
                    relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
                    reachability=ReachabilityClass.R5_CORPORATE_ONLY,
                    action=ActionMode.GENERIC_EMAIL_LAST_RESORT,
                    source="web_search",
                    extra={"company_associated": False, "mailbox_company_evidence": "UNKNOWN"},
                )
            ]
        elif kind in {"rh_blocked", "press_blocked"}:
            local = "rh" if kind == "rh_blocked" else "imprensa"
            routes = [
                _route(
                    cnpj,
                    f"{local}@{domain}",
                    channel=ChannelType.GENERIC_CORPORATE_EMAIL,
                    relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
                    reachability=ReachabilityClass.R5_CORPORATE_ONLY,
                    action=ActionMode.GENERIC_EMAIL_LAST_RESORT,
                    extra={"company_associated": True},
                )
            ]
        elif kind == "inferred_only":
            extra["domain_resolution"] = {"canonical_domain": domain}
            hyps = departmental_hypothesis_mailboxes(
                domain=domain,
                already=set(),
                has_observed_usable_route=False,
            )
            routes = [
                _route(
                    cnpj,
                    mailbox,
                    channel=ChannelType.INFERRED_DIRECT_EMAIL,
                    relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
                    reachability=ReachabilityClass.INFERRED_UNVERIFIED,
                    action=ActionMode.NEEDS_ENRICHMENT,
                    epistemic=EpistemicClass.INFERRED,
                    source="departmental_hypothesis",
                    extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL"},
                )
                for mailbox in hyps
            ]
        elif kind == "multi_mailbox":
            routes = [
                _route(
                    cnpj,
                    f"licitacao@{domain}",
                    channel=ChannelType.ROLE_MAILBOX,
                    relation=RouteRelation.ROUTES_TO_ROLE,
                    reachability=ReachabilityClass.R4_ROLE_ROUTE,
                    action=ActionMode.ROLE_EMAIL,
                    extra={"company_associated": True},
                ),
                _route(
                    cnpj,
                    f"contato@{domain}",
                    channel=ChannelType.GENERIC_CORPORATE_EMAIL,
                    relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
                    reachability=ReachabilityClass.R5_CORPORATE_ONLY,
                    action=ActionMode.GENERIC_EMAIL_LAST_RESORT,
                    extra={"company_associated": True},
                ),
            ]
        ledger = SearchLedger(provider_attempts=2 if kind != "no_email" else 1, documents_checked=3)
        accounts.append(
            AccountInvestigation(
                company_entity_id=cnpj,
                cnpj=cnpj,
                legal_name=f"EMPRESA {index:03d} ENGENHARIA LTDA",
                service_context="reajuste_14133",
                why_now="contrato ativo",
                routes=routes,
                ledger=ledger,
                extra=extra,
            )
        )
    return accounts


def run_cohort_funnel(n: int = 120) -> dict[str, Any]:
    accounts = build_real_shaped_cohort(n)
    payload = funnel(accounts)
    preferred_ok = 0
    double = 0
    for account in accounts:
        ranking = classify_account_email_routes(account)
        flags = sum(1 for item in ranking.classified_routes if item.preferred_initial)
        if flags > 1:
            double += 1
        if flags <= 1:
            preferred_ok += 1
    payload.update(
        {
            "schema_id": COHORT_SCHEMA,
            "auto_send": AUTO_SEND,
            "REAL_EMAIL_SENT": False,
            "accounts_with_at_most_one_preferred": preferred_ok,
            "accounts_with_two_preferred": double,
            "cohort_n": len(accounts),
        }
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controlled-email reachability funnel. Never sends mail.")
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    payload = run_cohort_funnel(args.n)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
