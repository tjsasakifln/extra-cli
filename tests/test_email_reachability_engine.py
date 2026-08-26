"""Adversarial coverage for the max-reachability controlled-email engine.

Drives shipped classify / rank / cascade / site-crawl / pattern / verify
functions. Does not send mail.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.confenge_contact_resolution.discovery.budget import DiscoveryBudget, InvestigationOutcome
from scripts.confenge_contact_resolution.discovery.cascade import DiscoveryCascade
from scripts.confenge_contact_resolution.discovery.official_domain import DomainClass, DomainResolution
from scripts.confenge_contact_resolution.discovery.site_crawl import SiteCrawlResult
from scripts.confenge_contact_resolution.mailbox_purpose import (
    PURPOSE_ETHICS_OMBUDSMAN,
    PURPOSE_FINANCEIRO,
    PURPOSE_NOREPLY,
    PURPOSE_PRESS,
    PURPOSE_PRIVACY_DPO,
    PURPOSE_WEBMASTER_ABUSE,
    classify_mailbox_purpose,
    is_mailbox_controlled_eligible,
)
from scripts.decision_unit_intelligence.benchmark import funnel
from scripts.decision_unit_intelligence.controlled_email import (
    EmailRouteClass,
    alternative_after_preferred_bounce,
    classify_account_email_routes,
    departmental_hypothesis_mailboxes,
    discovery_should_stop_for_commercial_value,
    evaluate_controlled_email_eligible,
    observed_contact_is_controlled_eligible_company_route,
    stamp_and_rank_feed_contacts,
)
from scripts.decision_unit_intelligence.controlled_email_cohort import (
    STORED_ICP_INPUT,
    load_stored_icp_accounts,
    run_cohort_funnel,
)
from scripts.decision_unit_intelligence.email_patterns.engine import InjectedTechnicalAdapter
from scripts.decision_unit_intelligence.email_verification import PassiveEmailVerifier
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelType,
    EpistemicClass,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
)
from scripts.decision_unit_intelligence.query_planner import should_early_stop
from scripts.decision_unit_intelligence.query_planner.spec import QueryExecution, QueryFamily, QueryPolicy, QuerySpec
from scripts.decision_unit_intelligence.site_contact_crawl import (
    SITE_GENERIC_ONLY,
    extract_site_contacts,
)
from scripts.decision_unit_intelligence.web_discovery import CrawlDocument
from scripts.warmbly_bridge.mapping import map_lead

ACCOUNT = "12345678000190"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "site_contact_crawl" / "empresaexemplo.com.br"


def _route(mailbox: str, **kwargs) -> ReachabilityRoute:
    extra = dict(kwargs.pop("extra", None) or {})
    return ReachabilityRoute(
        route_id=f"r-{mailbox}",
        company_entity_id=ACCOUNT,
        channel_type=kwargs.get("channel", ChannelType.GENERIC_CORPORATE_EMAIL),
        reachability_class=kwargs.get("reachability", ReachabilityClass.R5_CORPORATE_ONLY),
        action_mode=kwargs.get("action", ActionMode.GENERIC_EMAIL_LAST_RESORT),
        channel_value=mailbox,
        route_relation=kwargs.get("relation", RouteRelation.ACCOUNT_LEVEL_ONLY),
        epistemic_class=kwargs.get("epistemic", EpistemicClass.OBSERVED),
        source_type=kwargs.get("source_type", "company_website"),
        source_url=kwargs.get("source_url", "https://empresaexemplo.com.br/contato"),
        evidence_ids=["ev-public-route"],
        observed_at=kwargs.get("observed_at", "2026-08-21T12:00:00Z"),
        ownership=kwargs.get("ownership", OwnershipStatus.COMPANY_OWNED),
        suppression=kwargs.get("suppression", SuppressionState.NONE),
        extra=extra,
        reason_codes=list(kwargs.get("reason_codes") or []),
    )


def _account(routes: list[ReachabilityRoute]) -> AccountInvestigation:
    return AccountInvestigation(
        company_entity_id=ACCOUNT,
        cnpj=ACCOUNT,
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service_context="reajuste_14133",
        why_now="contrato ativo",
        routes=routes,
    )


def _doc(html: str, url: str) -> CrawlDocument:
    return CrawlDocument(
        url=url,
        text=" ",
        content_type="text/html",
        retrieved_at="2026-08-21T12:00:00Z",
        html=html,
        bytes_touched=len(html.encode()),
    )


def test_official_site_comercial_is_role_and_control_eligible() -> None:
    html = """
    <html><body>
      <h1>Comercial</h1>
      <a href="mailto:comercial@empresaexemplo.com.br">comercial@empresaexemplo.com.br</a>
    </body></html>
    """
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/comercial"), canonical_domain="empresaexemplo.com.br"
    )
    hit = next(item for item in records if item.email == "comercial@empresaexemplo.com.br")
    assert hit.associated is False
    assert hit.person_name is None
    route = _route(
        "comercial@empresaexemplo.com.br",
        channel=ChannelType.ROLE_MAILBOX,
        relation=RouteRelation.ROUTES_TO_ROLE,
        extra={"company_associated": True},
    )
    classified = evaluate_controlled_email_eligible(route)
    assert classified.route_class == EmailRouteClass.ROLE_OR_DEPARTMENT
    assert classified.controlled_email_eligible is True
    assert classified.mailbox_company_evidence == "OBSERVED"
    assert classified.mailbox_person_evidence == "UNKNOWN"
    assert classified.person_name is None


def test_official_footer_licitacao_is_company_route_not_junk() -> None:
    html = (FIXTURE_ROOT / "licitacoes.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/licitacoes"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = next(item for item in records if item.email == "licitacao@empresaexemplo.com.br")
    assert hit.associated is False
    assert hit.person_name is None
    assert SITE_GENERIC_ONLY in hit.reason_codes
    classified = evaluate_controlled_email_eligible(
        _route(
            "licitacao@empresaexemplo.com.br",
            channel=ChannelType.ROLE_MAILBOX,
            relation=RouteRelation.ROUTES_TO_ROLE,
            extra={"company_associated": True, "site_association_strength": "company_only"},
        )
    )
    assert classified.route_class == EmailRouteClass.ROLE_OR_DEPARTMENT
    assert classified.controlled_email_eligible is True


def test_contact_page_contato_is_generic_company() -> None:
    html = (FIXTURE_ROOT / "contato.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/contato"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = next(item for item in records if item.email == "contato@empresaexemplo.com.br")
    assert hit.person_name is None
    classified = evaluate_controlled_email_eligible(_route("contato@empresaexemplo.com.br"))
    assert classified.route_class == EmailRouteClass.GENERIC_COMPANY
    assert classified.controlled_email_eligible is True


def test_official_site_gmail_may_be_public_company_freemail() -> None:
    html = """
    <html><body>
      <p>Fale com a empresa: contato.empresa@gmail.com</p>
    </body></html>
    """
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/contato"), canonical_domain="empresaexemplo.com.br"
    )
    emails = {item.email for item in records}
    assert "contato.empresa@gmail.com" in emails
    classified = evaluate_controlled_email_eligible(
        _route(
            "contato.empresa@gmail.com",
            extra={
                "company_associated": True,
                "mailbox_company_evidence": "OBSERVED",
                "official_domain": "empresaexemplo.com.br",
            },
        )
    )
    assert classified.route_class == EmailRouteClass.PUBLIC_COMPANY_FREEMAIL
    assert classified.controlled_email_eligible is True


def test_snippet_only_gmail_stays_risky() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "fulano@gmail.com",
            source_type="web_search",
            ownership=OwnershipStatus.UNKNOWN,
            extra={"company_associated": False, "mailbox_company_evidence": "UNKNOWN"},
        )
    )
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.controlled_email_eligible is False


def test_web_search_gmail_unsubscribe_evidence_is_not_eligible() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "ll@sustainconsulting.llc",
            source_type="web_search",
            source_url="https://multisend-unsubscribe.gmail.com/uc",
            ownership=OwnershipStatus.COMPANY_OWNED,
            extra={
                "company_associated": True,
                "official_domain": "zancoconstrutora.com.br",
            },
        )
    )
    assert classified.controlled_email_eligible is False
    assert classified.mailbox_company_evidence == "UNKNOWN"


def test_empty_provenance_does_not_mint_company_website() -> None:
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "customerservice@uptodate.com",
                "ownership_status": "COMPANY_OWNED",
            }
        ],
        account_id=ACCOUNT,
        official_domain="oceanus.com.br",
    )
    assert stamped[0]["controlled_email_eligible"] is False
    assert not stamped[0].get("preferred_initial")


def test_blocked_mailboxes_are_not_control_eligible() -> None:
    cases = {
        "rh@empresaexemplo.com.br": None,
        "imprensa@empresaexemplo.com.br": PURPOSE_PRESS,
        "financeiro@empresaexemplo.com.br": PURPOSE_FINANCEIRO,
        "noreply@empresaexemplo.com.br": PURPOSE_NOREPLY,
        "dpo@empresaexemplo.com.br": PURPOSE_PRIVACY_DPO,
        "etica@empresaexemplo.com.br": PURPOSE_ETHICS_OMBUDSMAN,
        "webmaster@empresaexemplo.com.br": PURPOSE_WEBMASTER_ABUSE,
        "abuse@empresaexemplo.com.br": PURPOSE_WEBMASTER_ABUSE,
    }
    for mailbox, purpose in cases.items():
        mp = classify_mailbox_purpose(mailbox)
        if purpose is not None:
            assert mp.purpose == purpose, mailbox
        assert is_mailbox_controlled_eligible(mailbox) is False, mailbox
        classified = evaluate_controlled_email_eligible(_route(mailbox))
        assert classified.controlled_email_eligible is False, mailbox


def test_third_party_adv_br_is_risky() -> None:
    classified = evaluate_controlled_email_eligible(
        _route("contato@silva.adv.br", ownership=OwnershipStatus.UNKNOWN, extra={"company_associated": False})
    )
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.controlled_email_eligible is False
    assert "third_party_professional_domain" in classified.reason_codes


def test_homonymous_non_company_domain_is_risky() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "contato@outra-empresa.com.br",
            ownership=OwnershipStatus.UNKNOWN,
            extra={"company_associated": False, "mailbox_company_evidence": "UNKNOWN"},
        )
    )
    assert classified.controlled_email_eligible is False


def test_obfuscated_email_recovered_on_official_site() -> None:
    html = "<p>licitacao [at] empresaexemplo [dot] com [dot] br</p>"
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/"), canonical_domain="empresaexemplo.com.br"
    )
    emails = {item.email for item in records}
    assert "licitacao@empresaexemplo.com.br" in emails


def test_js_only_site_does_not_invent_mailbox() -> None:
    html = "<html><body>" + "".join(f"<script>var x{i}=1</script>" for i in range(6)) + "</body></html>"
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/"), canonical_domain="empresaexemplo.com.br"
    )
    assert all(item.email is None for item in records)


def test_two_sources_same_mailbox_dedupe_and_one_preferred() -> None:
    stamped = stamp_and_rank_feed_contacts(
        [
            {
                "email": "comercial@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://empresaexemplo.com.br/",
                "observed_at": "2026-08-24T12:00:00Z",
            },
            {
                "email": "COMERCIAL@empresaexemplo.com.br",
                "ownership_status": "COMPANY_OWNED",
                "source_url": "https://empresaexemplo.com.br/contato",
                "observed_at": "2026-08-24T12:00:00Z",
            },
        ],
        account_id=ACCOUNT,
    )
    mails = [c["email"] for c in stamped if c.get("email")]
    assert mails.count("comercial@empresaexemplo.com.br") == 1
    assert sum(1 for c in stamped if c.get("preferred_initial")) == 1
    assert sum(1 for c in stamped if c.get("recommended")) == 1
    assert stamped[0]["recommended"] is True
    assert stamped[0]["corroborated"] is True


def test_nominal_mailbox_with_company_association_is_generic_not_person() -> None:
    classified = evaluate_controlled_email_eligible(
        _route("joao.silva@empresaexemplo.com.br", channel=ChannelType.DIRECT_EMAIL)
    )
    assert classified.route_class == EmailRouteClass.GENERIC_COMPANY
    assert classified.controlled_email_eligible is True
    assert classified.mailbox_company_evidence == "OBSERVED"
    assert classified.mailbox_person_evidence == "UNKNOWN"
    assert classified.person_id is None
    assert classified.person_name is None
    assert classified.email_validated is False


def test_pattern_generated_stays_inferred_risky() -> None:
    classified = evaluate_controlled_email_eligible(
        _route(
            "ana.souza@empresaexemplo.com.br",
            channel=ChannelType.INFERRED_DIRECT_EMAIL,
            epistemic=EpistemicClass.INFERRED,
            extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL"},
            reason_codes=["INFERRED"],
        )
    )
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
    assert classified.provenance == "INFERRED"
    assert classified.controlled_email_eligible is False
    assert classified.epistemic_class == EpistemicClass.INFERRED.value


def test_conflicting_pattern_and_catchall_do_not_mint_identity() -> None:
    adapter = InjectedTechnicalAdapter(
        mx_by_domain={"empresaexemplo.com.br": "MX_PRESENT"},
        catch_all_by_domain={"empresaexemplo.com.br": "CATCH_ALL"},
    )
    check = adapter.check("ana.souza@empresaexemplo.com.br")
    assert check.mx == "MX_PRESENT"
    assert check.catch_all == "CATCH_ALL"
    classified = evaluate_controlled_email_eligible(
        _route(
            "ana.souza@empresaexemplo.com.br",
            channel=ChannelType.INFERRED_DIRECT_EMAIL,
            epistemic=EpistemicClass.INFERRED,
            extra={"mx_catch_all": "CATCH_ALL", "email_discovery_class": "INFERRED_PATTERN_CATCH_ALL"},
        )
    )
    assert classified.controlled_email_eligible is False
    assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY


def test_nxdomain_rejects_impossible_domain() -> None:
    class _Nx:
        def query(self, domain: str, record_type: str) -> list[str]:
            from scripts.decision_unit_intelligence.email_verification import DnsLookupError

            raise DnsLookupError("NXDOMAIN")

    report = PassiveEmailVerifier(_Nx()).verify("x@naoexiste-xyz-confenge.com.br")
    assert report.dns == "NXDOMAIN"
    assert report.final_classification == "REJECTED_IMPOSSIBLE_DOMAIN"
    classified = evaluate_controlled_email_eligible(
        _route(
            "x@naoexiste-xyz-confenge.com.br",
            extra={"email_verification": report.to_dict(), "dns": "NXDOMAIN"},
        )
    )
    assert classified.controlled_email_eligible is False
    assert "impossible_domain" in classified.reason_codes or "nxdomain" in classified.reason_codes


def test_preferred_bounce_promotes_alternative() -> None:
    ranking = classify_account_email_routes(
        _account(
            [
                _route(
                    "comercial@empresaexemplo.com.br",
                    channel=ChannelType.ROLE_MAILBOX,
                    relation=RouteRelation.ROUTES_TO_ROLE,
                    suppression=SuppressionState.HARD_BOUNCE,
                ),
                _route("contato@empresaexemplo.com.br"),
            ]
        )
    )
    nxt = alternative_after_preferred_bounce(ranking, bounced_mailbox="comercial@empresaexemplo.com.br")
    assert nxt is not None
    assert nxt.mailbox == "contato@empresaexemplo.com.br"


def test_non_reply_and_suppression_contract() -> None:
    alive = evaluate_controlled_email_eligible(_route("contato@empresaexemplo.com.br", extra={"non_reply": True}))
    assert alive.controlled_email_eligible is True
    opted = evaluate_controlled_email_eligible(
        _route("contato@empresaexemplo.com.br", suppression=SuppressionState.OPT_OUT)
    )
    assert opted.controlled_email_eligible is False
    assert "opt_out" in opted.reason_codes


def test_departmental_hypotheses_only_without_observed_route() -> None:
    none = departmental_hypothesis_mailboxes(
        domain="empresaexemplo.com.br",
        has_observed_usable_route=True,
    )
    assert none == ()
    hyps = departmental_hypothesis_mailboxes(domain="empresaexemplo.com.br", has_observed_usable_route=False)
    assert 1 <= len(hyps) <= 3
    for mailbox in hyps:
        classified = evaluate_controlled_email_eligible(
            _route(
                mailbox,
                channel=ChannelType.INFERRED_DIRECT_EMAIL,
                epistemic=EpistemicClass.INFERRED,
                extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL"},
            )
        )
        assert classified.route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY
        assert classified.controlled_email_eligible is False


def test_stop_early_on_observed_licitacao_skips_person_search(monkeypatch) -> None:
    search_calls = {"n": 0}

    class _Provider:
        available = True

        def search(self, query, max_results=3):
            search_calls["n"] += 1
            return []

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.probe_official_domain",
        lambda **kwargs: DomainResolution(
            domain="alphaengenharia.com.br",
            domain_class=DomainClass.OFFICIAL_CONFIRMED.value,
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.crawl_official_site",
        lambda domain, **kwargs: SiteCrawlResult(
            domain=domain,
            contacts=[
                {
                    "email": "licitacao@alphaengenharia.com.br",
                    "source_url": f"https://{domain}/",
                    "observed_at": "2026-08-21T12:00:00Z",
                }
            ],
            pages=[{"url": f"https://{domain}/", "contacts": [{"email": "licitacao@alphaengenharia.com.br"}]}],
        ),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.lookup_public_docs_for_cnpj",
        lambda *args, **kwargs: [],
    )
    cascade = DiscoveryCascade(
        budget=DiscoveryBudget(max_search_queries=8, max_pages=8, max_total_requests=20),
        web_provider=_Provider(),
        allow_network=True,
        dsn=None,
    )
    result = cascade.run(
        cnpj14="11222333000181",
        razao_social="ALPHA ENGENHARIA E CONSTRUCOES LTDA",
        stop_when_strong_contact=True,
    )
    assert result.stats.outcome == InvestigationOutcome.CONTACT_FOUND.value
    assert result.stats.stop_reason == "official_site_controlled_eligible_route"
    assert search_calls["n"] == 0
    classified = evaluate_controlled_email_eligible(
        _route(
            "licitacao@alphaengenharia.com.br",
            channel=ChannelType.ROLE_MAILBOX,
            relation=RouteRelation.ROUTES_TO_ROLE,
            source_url="https://alphaengenharia.com.br/",
            extra={"official_domain": "alphaengenharia.com.br"},
        )
    )
    assert discovery_should_stop_for_commercial_value([classified]) is True


def _cascade_with_site_email(monkeypatch, email: str):
    search_calls = {"n": 0}

    class _Provider:
        available = True

        def search(self, query, max_results=3):
            search_calls["n"] += 1
            return []

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.probe_official_domain",
        lambda **kwargs: DomainResolution(
            domain="alphaengenharia.com.br",
            domain_class=DomainClass.OFFICIAL_CONFIRMED.value,
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.crawl_official_site",
        lambda domain, **kwargs: SiteCrawlResult(
            domain=domain,
            contacts=[
                {
                    "email": email,
                    "source_url": f"https://{domain}/",
                    "observed_at": "2026-08-21T12:00:00Z",
                }
            ],
            pages=[{"url": f"https://{domain}/", "contacts": [{"email": email}]}],
        ),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.lookup_public_docs_for_cnpj",
        lambda *args, **kwargs: [],
    )
    cascade = DiscoveryCascade(
        budget=DiscoveryBudget(max_search_queries=4, max_pages=4, max_total_requests=12),
        web_provider=_Provider(),
        allow_network=True,
        dsn=None,
    )
    result = cascade.run(
        cnpj14="11222333000181",
        razao_social="ALPHA ENGENHARIA E CONSTRUCOES LTDA",
        stop_when_strong_contact=True,
    )
    return result, search_calls


def test_nominal_mailbox_with_official_company_association_stops_cascade(monkeypatch) -> None:
    result, search_calls = _cascade_with_site_email(monkeypatch, "joao.silva@alphaengenharia.com.br")
    assert result.stats.stop_reason == "official_site_controlled_eligible_route"
    assert search_calls["n"] == 0
    assert (
        observed_contact_is_controlled_eligible_company_route(
            {
                "email": "joao.silva@alphaengenharia.com.br",
                "source": "company_website",
                "observed_at": "2026-08-21T12:00:00Z",
            },
            official_domain="alphaengenharia.com.br",
        )
        is True
    )


def test_third_party_adv_br_on_site_does_not_stop_cascade(monkeypatch) -> None:
    result, search_calls = _cascade_with_site_email(monkeypatch, "contato@silva.adv.br")
    assert result.stats.stop_reason != "official_site_controlled_eligible_route"
    assert search_calls["n"] >= 1
    assert (
        observed_contact_is_controlled_eligible_company_route(
            {"email": "contato@silva.adv.br", "source": "company_website"},
            official_domain="alphaengenharia.com.br",
        )
        is False
    )


def test_no_control_eligible_route_keeps_searching(monkeypatch) -> None:
    search_calls = {"n": 0}

    class _Provider:
        available = True

        def search(self, query, max_results=3):
            search_calls["n"] += 1
            return []

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.probe_official_domain",
        lambda **kwargs: DomainResolution(
            domain="alphaengenharia.com.br",
            domain_class=DomainClass.OFFICIAL_CONFIRMED.value,
            confidence=0.9,
        ),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.crawl_official_site",
        lambda domain, **kwargs: SiteCrawlResult(
            domain=domain,
            contacts=[{"email": "rh@alphaengenharia.com.br"}],
            pages=[],
        ),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.lookup_public_docs_for_cnpj",
        lambda *args, **kwargs: [],
    )
    cascade = DiscoveryCascade(
        budget=DiscoveryBudget(max_search_queries=4, max_pages=4, max_total_requests=12),
        web_provider=_Provider(),
        allow_network=True,
        dsn=None,
    )
    result = cascade.run(
        cnpj14="11222333000181",
        razao_social="ALPHA ENGENHARIA E CONSTRUCOES LTDA",
        stop_when_strong_contact=True,
    )
    assert result.stats.stop_reason != "official_site_controlled_eligible_route"
    assert search_calls["n"] >= 1


def test_query_planner_early_stop_on_control_eligible_email() -> None:
    spec = QuerySpec(QueryFamily.SITE_PATH, "contato", 'site:empresaexemplo.com.br "contato"', ACCOUNT)
    row = QueryExecution(spec=spec, backend="replay", executed=True, control_eligible_email_count=1)
    policy = QueryPolicy(version="query-policy.v2", min_control_eligible_email=1)
    assert should_early_stop([row], policy) is True


def test_map_lead_recommended_aliases_preferred_initial() -> None:
    lead = map_lead(
        {
            "cnpj14": ACCOUNT,
            "razao_social": "EMPRESA EXEMPLO ENGENHARIA LTDA",
            "commercial_state": "NEW",
            "construction_universe_member": True,
            "official_domain": "empresaexemplo.com.br",
        },
        intel={
            "offer": {"service_code": "REAJUSTE"},
            "why_this_account": "objeto pavimentacao",
            "why_now": "aditivo recente",
            "observed_fact": "pavimentacao asfaltica",
            "evidence": [{"id": "ev-1", "type": "PNCP_CONTRACT", "epistemic_class": "CONFIRMED_FACT"}],
        },
        contacts_row={
            "cnpj14": ACCOUNT,
            "contacts": [
                {
                    "name": "",
                    "email": "comercial@empresaexemplo.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OBSERVED",
                    "email_explicitly_published": True,
                    "provenance": {
                        "source_type": "site",
                        "source_url": "https://empresaexemplo.com.br/contato",
                        "observed_at": "2026-08-12T12:00:00Z",
                    },
                },
                {
                    "name": "",
                    "email": "contato@empresaexemplo.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OBSERVED",
                    "email_explicitly_published": True,
                    "provenance": {
                        "source_type": "site",
                        "source_url": "https://empresaexemplo.com.br/",
                        "observed_at": "2026-08-12T12:00:00Z",
                    },
                },
            ],
        },
    )
    assert lead is not None
    preferred = [c for c in lead["contacts"] if c.get("preferred_initial")]
    recommended = [c for c in lead["contacts"] if c.get("recommended")]
    assert len(preferred) == 1
    assert recommended == preferred


def test_cohort_replays_stored_icp_observations() -> None:
    assert STORED_ICP_INPUT.is_file()
    accounts = load_stored_icp_accounts(limit=200)
    assert len(accounts) >= 100
    stored_ids = []
    for line in STORED_ICP_INPUT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        stored_ids.append(json.loads(line)["cnpj14"])
        if len(stored_ids) >= 200:
            break
    replay_ids = [account.cnpj for account in accounts]
    assert replay_ids == stored_ids
    assert len(set(replay_ids)) == len(accounts)
    payload = funnel(accounts)
    for key in (
        "accounts",
        "official_domain_proven",
        "any_public_email_observed",
        "DIRECT_PERSON",
        "ROLE_OR_DEPARTMENT",
        "GENERIC_COMPANY",
        "PUBLIC_COMPANY_FREEMAIL",
        "PROBABILISTIC_OR_RISKY",
        "controlled_email_eligible",
        "preferred_initial_route",
        "auto_send",
    ):
        assert key in payload
    assert payload["auto_send"] is False
    assert payload["accounts"] == len(accounts) == 200
    assert payload["double_preferred_accounts"] == 0
    first = run_cohort_funnel(200)
    second = run_cohort_funnel(200)
    assert first["hand_built_class_mix"] is False
    assert first["controlled_email_eligible"] == second["controlled_email_eligible"]
    assert first["REAL_EMAIL_SENT"] is False
    assert first["accounts_with_two_preferred"] == 0
    assert first["observation_source"].endswith("real-1000-input.jsonl")


def test_a_social_page_is_never_an_official_company_domain():
    """A Facebook page in the website column made every gmail on it OBSERVED."""
    from scripts.warmbly_bridge.mapping import official_domain_host

    for shared in (
        "https://www.facebook.com/construtoraalvo",
        "https://instagram.com/construtoraalvo",
        "https://linkedin.com/company/construtoraalvo",
        "https://cnpja.com/office/12345678000195",
        "https://pncp.gov.br/app/editais/1",
        # Anyone can publish on these too, so a page here owns nothing.
        "https://construtoraalvo.blogspot.com",
        "https://construtoraalvo.wordpress.com",
        "https://construtoraalvo.notion.site",
        "https://construtoraalvo.github.io",
        "https://construtoraalvo.negocio.site",
        "https://linktr.ee/construtoraalvo",
        "https://medium.com/@construtoraalvo",
        "https://bit.ly/construtoraalvo",
        "https://web.archive.org/web/2026/http://x",
        "https://wa.me/5511999999999",
        "https://t.me/construtoraalvo",
        "https://docs.google.com/document/d/x",
    ):
        assert official_domain_host(shared) == "", shared

    assert official_domain_host("https://www.construtoraalvo.com.br/contato") == "construtoraalvo.com.br"


def test_an_ambiguous_shared_preferred_mailbox_fails_closed_across_runs():
    """Feed ordering must never choose which legal identity owns a mailbox."""
    from scripts.decision_unit_intelligence.controlled_email import (
        apply_cross_account_preferred_mailbox_gate,
    )

    def lead(cnpj14: str, watermark: str) -> dict:
        return {
            "source_lead_id": f"lead-{cnpj14}",
            "target_fit_source_watermark": watermark,
            "company": {"cnpj14": cnpj14},
            "contacts": [{"email": "contato@grupo.com.br", "preferred_initial": True, "recommended": True}],
        }

    def winners(leads: list[dict]) -> list[str]:
        return [
            item["company"]["cnpj14"]
            for item in apply_cross_account_preferred_mailbox_gate(leads)
            if any(c.get("preferred_initial") for c in item["contacts"])
        ]

    first = [lead("11111111000191", "2026-08-19T00:00:00Z"), lead("22222222000172", "2026-08-20T00:00:00Z")]
    # A refresh moves account A's watermark past B's, flipping feed order.
    second = [lead("22222222000172", "2026-08-20T00:00:00Z"), lead("11111111000191", "2026-08-21T00:00:00Z")]

    assert winners(first) == winners(second) == []
