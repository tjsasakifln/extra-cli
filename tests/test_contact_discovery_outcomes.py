"""Unit contracts for auditable per-account contact-discovery outcomes."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from scripts.decision_unit_intelligence.batch_outcomes import classify_account, persist_outcome
from scripts.decision_unit_intelligence.batch_queue import ClaimedDiscoveryJob
from scripts.decision_unit_intelligence.batch_worker import default_discovery
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    AccountTerminal,
    ActionMode,
    ChannelType,
    EpistemicClass,
    FreshnessState,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SearchLedger,
)

ACCOUNT_ID = "12345678000190"


def _job(*, search_backend: str) -> ClaimedDiscoveryJob:
    return ClaimedDiscoveryJob(
        id=7,
        cohort_id="target-confirmed-20260824",
        canonical_account_id=ACCOUNT_ID,
        service="reajuste_14133",
        offer_context="confenge_outbound",
        discovery_policy_version="dui.policy.v1",
        search_backend=search_backend,
        budget_version="budget.test",
        code_sha="sha-test",
        input_evidence_version="target-fit.test",
        idempotency_key="idem-test",
        revision=1,
        domain_key="",
        backend_key=search_backend,
        cursor={},
        run_id="run-test",
        attempt_id=11,
        attempt_count=1,
        max_attempts=5,
        cancel_requested=False,
    )


def _account(*, with_role_route: bool) -> AccountInvestigation:
    routes: list[ReachabilityRoute] = []
    terminal = AccountTerminal.NEEDS_ENRICHMENT
    if with_role_route:
        routes.append(
            ReachabilityRoute(
                route_id="route-licitacoes",
                company_entity_id=ACCOUNT_ID,
                channel_type=ChannelType.ROLE_MAILBOX,
                reachability_class=ReachabilityClass.R4_ROLE_ROUTE,
                action_mode=ActionMode.ROLE_EMAIL,
                target_role="licitacoes",
                channel_value="licitacoes@empresaexemplo.com.br",
                route_relation=RouteRelation.ROUTES_TO_ROLE,
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="company_website",
                source_url="https://empresaexemplo.com.br/contato",
                evidence_ids=["evidence-contact-page"],
                freshness=FreshnessState.FRESH,
                ownership=OwnershipStatus.COMPANY_OWNED,
                observed_at="2026-08-24T12:00:00Z",
                extra={
                    "official_domain": "empresaexemplo.com.br",
                    "mailbox_company_evidence": "OBSERVED",
                    "mailbox_department_evidence": "OBSERVED",
                    "email_discovery_class": "ROLE_MAILBOX",
                },
            )
        )
        terminal = AccountTerminal.ACTIONABLE_ROUTE
    return AccountInvestigation(
        company_entity_id=ACCOUNT_ID,
        cnpj=ACCOUNT_ID,
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service_context="reajuste_14133",
        why_now="TARGET_CONFIRMED",
        routes=routes,
        terminal=terminal,
        ledger=SearchLedger(tiers_completed=[0, 1, 2, 3]),
    )


def test_role_route_output_is_ready_ranked_and_auditable(tmp_path: Path) -> None:
    outcome = persist_outcome(
        classify_account(_account(with_role_route=True)),
        job=_job(search_backend="searxng"),
        output_root=tmp_path,
    )

    payload = json.loads(Path(outcome.output_pointer or "").read_text(encoding="utf-8"))
    assert payload["schema_id"] == "confenge.contact_discovery.job_output.v2"
    assert payload["enrichment_state"] == "EMAIL_ROUTE_READY"
    projection = payload["contact_projection"]
    assert projection["preferred_initial_route"]["route_class"] == "ROLE_OR_DEPARTMENT"
    contact = projection["contacts"][0]
    assert contact["preferred_initial"] is True
    assert contact["email_validated"] is False
    assert contact["person_unknown"] is True
    assert contact["source"] == "company_website"
    assert contact["source_url"] == "https://empresaexemplo.com.br/contato"
    assert contact["source_reference"] == "https://empresaexemplo.com.br/contato"
    assert contact["evidence_ids"] == ["evidence-contact-page"]
    assert contact["observed_at"] == "2026-08-24T12:00:00Z"
    assert contact["mailbox_department"] == "licitacoes"
    assert contact["channel_epistemic_class"] == "OBSERVED"
    assert contact["risk_class"] == "ALLOWED"
    assert contact["route_suppression"] == "NONE"


def test_no_email_is_not_claimed_when_public_discovery_was_disabled(tmp_path: Path) -> None:
    outcome = persist_outcome(
        classify_account(_account(with_role_route=False)),
        job=_job(search_backend="off"),
        output_root=tmp_path,
    )

    payload = json.loads(Path(outcome.output_pointer or "").read_text(encoding="utf-8"))
    assert payload["enrichment_state"] == "BLOCKED_WITH_REASON"
    assert payload["enrichment_reason"] == "PUBLIC_DISCOVERY_DISABLED"


def test_completed_public_waterfall_can_end_without_email(tmp_path: Path) -> None:
    outcome = persist_outcome(
        classify_account(_account(with_role_route=False)),
        job=_job(search_backend="searxng"),
        output_root=tmp_path,
    )

    payload = json.loads(Path(outcome.output_pointer or "").read_text(encoding="utf-8"))
    assert payload["enrichment_state"] == "NO_PUBLIC_EMAIL_FOUND"
    assert payload["enrichment_reason"] == "WATERFALL_COMPLETED_WITHOUT_ELIGIBLE_ROUTE"


def test_provider_failure_cannot_be_reported_as_no_public_email(tmp_path: Path) -> None:
    account = _account(with_role_route=False)
    account.ledger.blocked_sources.append("company_website:ConnectError")
    outcome = persist_outcome(
        classify_account(account),
        job=_job(search_backend="searxng"),
        output_root=tmp_path,
    )

    payload = json.loads(Path(outcome.output_pointer or "").read_text(encoding="utf-8"))
    assert payload["enrichment_state"] == "BLOCKED_WITH_REASON"
    assert payload["enrichment_reason"] == "WATERFALL_PROVIDER_FAILURE"


def test_worker_replays_the_recorded_search_and_site_budgets(
    monkeypatch,
) -> None:  # noqa: ANN001
    import scripts.decision_unit_intelligence.batch_worker as batch_worker

    captured: dict = {}

    def fake_run_account(cnpj: str, **kwargs):  # noqa: ANN001, ANN202
        captured["cnpj"] = cnpj
        captured.update(kwargs)
        return "account"

    monkeypatch.setattr(batch_worker, "run_account", fake_run_account)
    job = replace(
        _job(search_backend="searxng"),
        cursor={
            "budget": {
                "searxng_url": "http://search.internal",
                "search_failover": "ddgs",
                "search_fallback": "off",
                "query_policy_version": "query-policy.test",
                "site_crawl": True,
                "site_crawl_baseline": True,
                "site_max_pages": 7,
                "site_max_depth": 2,
                "site_max_bytes": 700_000,
                "site_timeout_seconds": 9.0,
                "site_max_redirects": 3,
                "site_requests_per_minute": 11,
                "site_max_sitemap_urls": 33,
            }
        },
    )

    assert default_discovery(job) == "account"
    assert captured["search_backend"] == "searxng"
    assert captured["search_failover"] == "ddgs"
    assert captured["query_policy_version"] == "query-policy.test"
    assert captured["site_crawl_baseline"] is True
    assert captured["site_budget"].to_dict() == {
        "max_pages": 7,
        "max_depth": 2,
        "max_bytes": 700_000,
        "timeout_seconds": 9.0,
        "max_redirects": 3,
        "requests_per_minute": 11,
        "max_sitemap_urls": 33,
    }
