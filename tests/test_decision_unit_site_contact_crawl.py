"""Adversarial fixtures drive the shipped site-contact crawl, not a reimplementation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.company_website import CompanyWebsiteProvider
from scripts.decision_unit_intelligence.runner import run_account
from scripts.decision_unit_intelligence.site_contact_crawl import (
    SITE_GENERIC_ONLY,
    SITE_JS_BLOCKED,
    SITE_MAILTO_ASSOCIATED,
    SITE_NO_HIGH_VALUE_PATH,
    SITE_PROFILE_EMAIL,
    SITE_STALE_OR_UNKNOWN,
    SITE_STRUCTURED_CONTACT,
    SITE_TEAM_CARD_EMAIL,
    STRONG_SITE_CODES,
    MappingCrawler,
    SiteCrawlBudget,
    associate_site_email,
    canonicalize_site_url,
    contacts_to_observations,
    extract_site_contacts,
    load_fixture_corpus,
    parse_sitemap_urls,
    recover_broken_span_emails,
    recover_obfuscated_emails,
    run_site_contact_crawl,
    seed_corporate_site_urls,
    should_skip_site_url,
)
from scripts.decision_unit_intelligence.web_discovery import CrawlDocument

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "site_contact_crawl" / "empresaexemplo.com.br"


def _context() -> InvestigationContext:
    return InvestigationContext(
        cnpj="12345678000190",
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service="reajuste_14133",
    )


def _doc(html: str, url: str = "https://empresaexemplo.com.br/equipe") -> CrawlDocument:
    return CrawlDocument(
        url=url,
        text=" ",
        content_type="text/html",
        retrieved_at="2026-08-15T12:00:00Z",
        html=html,
        bytes_touched=len(html.encode()),
    )


def _named(records, email: str):
    return next(item for item in records if item.email == email)


def test_canonicalize_strips_www_fragment_tracking_and_slash():
    clean = canonicalize_site_url("http://www.empresaexemplo.com.br/equipe/?utm_source=x&fbclid=1#topo")
    assert clean == "https://empresaexemplo.com.br/equipe"


def test_skip_list_covers_login_cart_webmail_search_calendar_combinatorial():
    blocked = [
        "https://empresaexemplo.com.br/login",
        "https://empresaexemplo.com.br/carrinho",
        "https://empresaexemplo.com.br/webmail/inbox",
        "https://empresaexemplo.com.br/busca?q=diretor",
        "https://empresaexemplo.com.br/search?s=equipe",
        "https://empresaexemplo.com.br/calendario/2026/08",
        "https://empresaexemplo.com.br/obras?page=1&sort=az&filter=sc",
    ]
    for url in blocked:
        skip, reason = should_skip_site_url(url)
        assert skip, url
        assert reason.startswith("skip:")
    allow, _reason = should_skip_site_url("https://empresaexemplo.com.br/equipe")
    assert allow is False


def test_seeds_homepage_search_hits_sitemap_robots_and_drop_skip_list():
    seeds = seed_corporate_site_urls(
        canonical_domain="empresaexemplo.com.br",
        extra_urls=["https://empresaexemplo.com.br/institucional/diretoria"],
        sitemap_urls=["https://empresaexemplo.com.br/equipe", "https://externo.example/x"],
        robots_sitemaps=["https://empresaexemplo.com.br/sitemap.xml"],
        internal_links=[
            ("https://empresaexemplo.com.br/contato", "Fale conosco"),
            ("https://empresaexemplo.com.br/login", "Entrar"),
        ],
    )
    urls = [item.url for item in seeds]
    assert "https://empresaexemplo.com.br/" in urls
    assert "https://empresaexemplo.com.br/equipe" in urls
    assert "https://empresaexemplo.com.br/institucional/diretoria" in urls
    assert "https://empresaexemplo.com.br/contato" in urls
    assert "https://empresaexemplo.com.br/sitemap.xml" in urls
    assert all("login" not in item.url for item in seeds)
    assert all("externo.example" not in item.url for item in seeds)
    assert seeds[0].score >= seeds[-1].score


def test_mailto_in_card_is_strong_team_association():
    html = """
    <html><body>
      <article class="card">
        <h3>João da Silva</h3>
        <p>Diretor de Engenharia</p>
        <a href="mailto:joao.silva@empresaexemplo.com.br">escrever</a>
      </article>
    </body></html>
    """
    records = extract_site_contacts(_doc(html), canonical_domain="empresaexemplo.com.br")
    hit = _named(records, "joao.silva@empresaexemplo.com.br")
    assert hit.associated is True
    assert hit.person_name == "João da Silva"
    assert SITE_TEAM_CARD_EMAIL in hit.reason_codes
    assert SITE_MAILTO_ASSOCIATED in hit.reason_codes
    assert set(hit.reason_codes) & STRONG_SITE_CODES


def test_same_official_page_cnpj_and_mailbox_emit_account_binding_evidence():
    html = """
    <html><body>
      <article class="card">
        <h3>João da Silva</h3>
        <p>Diretor de Engenharia</p>
        <a href="mailto:joao.silva@empresaexemplo.com.br">escrever</a>
      </article>
      <footer>CNPJ 12.345.678/0001-90</footer>
    </body></html>
    """
    records = extract_site_contacts(
        _doc(html),
        canonical_domain="empresaexemplo.com.br",
        target_cnpj=_context().cnpj,
    )
    _people, channels, evidence = contacts_to_observations(
        _context(),
        records,
        canonical_domain="empresaexemplo.com.br",
    )

    route = next(channel for channel in channels if channel.channel_value and "@" in channel.channel_value)
    assert route.extra["page_cnpj14"] == "12345678000190"
    assert route.extra["page_cnpj_evidence_id"] == route.evidence_id
    assert len(route.extra["page_cnpj_evidence_sha256"]) == 64
    assert any(item.field == "account_mailbox_binding" for item in evidence)


def test_cross_card_mailto_is_not_promoted(stop_the_line=True):
    html = Path(FIXTURE_ROOT / "cross-mailto.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/cross-mailto"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = _named(records, "joao.silva@empresaexemplo.com.br")
    assert hit.associated is False
    assert hit.person_name != "Maria Souza" or hit.associated is False
    assert not (set(hit.reason_codes) & STRONG_SITE_CODES and hit.associated)


def test_two_nearby_employees_stay_candidate():
    html = Path(FIXTURE_ROOT / "nearby.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/nearby"),
        canonical_domain="empresaexemplo.com.br",
    )
    emails = [item for item in records if item.email and "empresaexemplo.com.br" in item.email]
    assert emails
    assert all(item.associated is False for item in emails)
    assert all(not (set(item.reason_codes) & STRONG_SITE_CODES) for item in emails)
    associated, candidate, reasons, method = associate_site_email(
        email="joao.silva@empresaexemplo.com.br",
        person_name="João da Silva",
        other_visible_names=["Maria Souza"],
        mailto_in_block=False,
        unique_in_block=False,
        unique_on_profile=False,
        structured_coherent=False,
        generic=False,
        in_footer=False,
        stale=False,
        foreign_domain=False,
        js_blocked=False,
    )
    assert associated is False
    assert candidate is True
    assert method == "candidate_proximity_not_promoted"
    assert not (set(reasons) & STRONG_SITE_CODES)


def test_footer_generic_is_never_a_person():
    html = Path(FIXTURE_ROOT / "contato.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/contato"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = _named(records, "contato@empresaexemplo.com.br")
    assert hit.associated is False
    assert hit.person_name is None
    assert SITE_GENERIC_ONLY in hit.reason_codes


def test_individual_profile_is_site_profile_email():
    html = (FIXTURE_ROOT / "equipe" / "joao-da-silva.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/equipe/joao-da-silva"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = _named(records, "joao.silva@empresaexemplo.com.br")
    assert hit.associated is True
    assert hit.person_name == "João da Silva"
    assert SITE_PROFILE_EMAIL in hit.reason_codes or SITE_TEAM_CARD_EMAIL in hit.reason_codes


def test_jsonld_coherent_promotes_incoherent_does_not():
    coherent = Path(FIXTURE_ROOT / "structured.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(coherent, "https://empresaexemplo.com.br/structured"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = _named(records, "helena.castro@empresaexemplo.com.br")
    assert hit.associated is True
    assert SITE_STRUCTURED_CONTACT in hit.reason_codes or SITE_TEAM_CARD_EMAIL in hit.reason_codes

    incoherent = """
    <html><head>
      <script type="application/ld+json">
      {"@type":"Person","name":"João da Silva","email":"joao.silva@empresaexemplo.com.br","jobTitle":"Diretor"}
      </script>
    </head>
    <body><h1>Maria Souza</h1><p>Gerente Comercial</p></body></html>
    """
    bad = extract_site_contacts(
        _doc(incoherent, "https://empresaexemplo.com.br/incoherent"),
        canonical_domain="empresaexemplo.com.br",
    )
    joao = [item for item in bad if item.email == "joao.silva@empresaexemplo.com.br"]
    assert joao
    assert all(item.associated is False for item in joao)
    assert all(SITE_STRUCTURED_CONTACT not in item.reason_codes or not item.associated for item in joao)


def test_obfuscation_recovered_without_code_execution():
    text = "bruno.alves [at] empresaexemplo [dot] com [dot] br"
    assert "bruno.alves@empresaexemplo.com.br" in recover_obfuscated_emails(text)
    assert "paula.reis@empresaexemplo.com.br" in recover_obfuscated_emails("paula.reis&#64;empresaexemplo.com.br")
    html = "<p><span>diego.martins</span><span>@</span><span>empresaexemplo.com.br</span></p>"
    assert "diego.martins@empresaexemplo.com.br" in recover_broken_span_emails(html)
    records = extract_site_contacts(
        _doc(
            (FIXTURE_ROOT / "obfuscated.html").read_text(encoding="utf-8"), "https://empresaexemplo.com.br/obfuscated"
        ),
        canonical_domain="empresaexemplo.com.br",
    )
    recovered = {item.email for item in records}
    assert "bruno.alves@empresaexemplo.com.br" in recovered
    assert "paula.reis@empresaexemplo.com.br" in recovered
    assert "diego.martins@empresaexemplo.com.br" in recovered
    bruno = _named(records, "bruno.alves@empresaexemplo.com.br")
    assert bruno.associated is True
    assert SITE_TEAM_CARD_EMAIL in bruno.reason_codes


def test_holding_foreign_domain_is_not_promoted():
    html = Path(FIXTURE_ROOT / "holding.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/holding"),
        canonical_domain="empresaexemplo.com.br",
    )
    hit = _named(records, "joao.silva@holding-grupo.com.br")
    assert hit.associated is False
    assert SITE_STALE_OR_UNKNOWN in hit.reason_codes


def test_huge_sitemap_stops_at_published_budget():
    xml = (FIXTURE_ROOT / "sitemap.xml").read_text(encoding="utf-8")
    budget = SiteCrawlBudget(max_sitemap_urls=80, max_pages=12, max_depth=2, timeout_seconds=5.0)
    parsed = parse_sitemap_urls(xml, limit=budget.max_sitemap_urls)
    assert len(parsed) == 80
    assert len(parsed) < xml.count("<loc>")
    crawler, domain = load_fixture_corpus(FIXTURE_ROOT)
    result = run_site_contact_crawl(
        crawler=crawler,
        context=_context(),
        canonical_domain=domain,
        budget=budget,
        rate_limit=False,
    )
    assert result.budget["pages"] <= budget.max_pages
    assert result.budget["bytes_touched"] <= budget.max_bytes
    assert len(result.visited) <= budget.max_pages
    assert result.stop_reason in {"BUDGET_PAGES", "BUDGET_SITEMAP", "BUDGET_TIME", "COMPLETE"}


def test_external_redirect_is_not_followed_off_domain():
    crawler = MappingCrawler(
        {
            "https://empresaexemplo.com.br/": "<html><a href='/parceiro'>parceiro</a></html>",
            "https://externo.example/oferta": "<html><a href='mailto:x@externo.example'>x</a></html>",
        },
        redirects={"https://empresaexemplo.com.br/parceiro": "https://externo.example/oferta"},
    )
    result = run_site_contact_crawl(
        crawler=crawler,
        context=_context(),
        canonical_domain="empresaexemplo.com.br",
        seed_urls=["https://empresaexemplo.com.br/parceiro"],
        budget=SiteCrawlBudget(max_pages=4, max_depth=2, timeout_seconds=5.0),
        rate_limit=False,
    )
    assert all("externo.example" not in url for url in result.visited)
    assert any("external-redirect" in item for item in result.skipped)
    assert not any(item.email == "x@externo.example" and item.associated for item in result.contacts)


def test_skip_list_paths_are_not_queued_from_homepage():
    crawler, domain = load_fixture_corpus(FIXTURE_ROOT)
    result = run_site_contact_crawl(
        crawler=crawler,
        context=_context(),
        canonical_domain=domain,
        budget=SiteCrawlBudget(max_pages=8, max_depth=2, timeout_seconds=5.0),
        rate_limit=False,
    )
    assert not any("/login" in url for url in result.visited)
    assert not any("/carrinho" in url for url in result.visited)
    assert not any("busca" in url for url in result.visited)


def test_js_heavy_page_emits_site_js_blocked():
    html = Path(FIXTURE_ROOT / "js-heavy.html").read_text(encoding="utf-8")
    records = extract_site_contacts(
        _doc(html, "https://empresaexemplo.com.br/js-heavy"),
        canonical_domain="empresaexemplo.com.br",
    )
    assert any(SITE_JS_BLOCKED in item.reason_codes for item in records)
    assert all(not item.associated for item in records)


def test_full_fixture_crawl_yields_named_email_and_rejects_footer():
    crawler, domain = load_fixture_corpus(FIXTURE_ROOT)
    result = run_site_contact_crawl(
        crawler=crawler,
        context=_context(),
        canonical_domain=domain,
        seed_urls=["https://empresaexemplo.com.br/equipe"],
        budget=SiteCrawlBudget(max_pages=12, max_depth=3, timeout_seconds=8.0),
        rate_limit=False,
    )
    assert result.high_value_urls
    named = [item for item in result.channels if item.extra.get("identity_explicitly_associated")]
    assert named
    assert any(set(item.extra.get("association_reason_codes") or []) & STRONG_SITE_CODES for item in named)
    footer = [item for item in result.channels if item.channel_value == "contato@empresaexemplo.com.br"]
    assert footer
    assert all(item.person_name is None for item in footer)
    assert all(item.extra.get("identity_explicitly_associated") is False for item in footer)
    assert result.budget["pages"] <= 12
    assert result.metrics["false_association"] == 0


def test_company_website_provider_consumes_isolated_layer():
    crawler, domain = load_fixture_corpus(FIXTURE_ROOT)
    provider = CompanyWebsiteProvider(
        crawler=crawler,
        site_budget=SiteCrawlBudget(max_pages=10, max_depth=2, timeout_seconds=8.0),
    )
    ctx = _context()
    ctx.extra["company_site"] = f"https://{domain}"
    ctx.extra["domain_resolution"] = {"canonical_domain": domain, "confidence": "HIGH"}
    ctx.extra["search_hit_urls"] = [f"https://{domain}/equipe"]
    result = provider.collect(ctx)
    assert result.terminal == "hit"
    assert result.attempts[0].provider_id == "company_website"
    assert result.attempts[0].extra["site_crawl"]["metrics"]["named_associated"] >= 1
    assert any(channel.extra.get("identity_explicitly_associated") for channel in result.channels)
    assert not any(
        channel.channel_value == "contato@empresaexemplo.com.br" and channel.person_name for channel in result.channels
    )


def test_run_account_wires_site_crawl_after_defensible_domain():
    crawler, domain = load_fixture_corpus(FIXTURE_ROOT)

    class KnownSite:
        provider_id = "known_site"
        tier = 0

        def collect(self, context):
            from scripts.decision_unit_intelligence.models import SearchAttempt, stable_id
            from scripts.decision_unit_intelligence.providers.base import ProviderResult

            return ProviderResult(
                legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
                company_site=f"https://{domain}",
                extra={"domain_resolution": {"canonical_domain": domain, "confidence": "HIGH"}},
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("known", context.cnpj),
                        company_entity_id=context.cnpj,
                        tier=0,
                        provider_id=self.provider_id,
                        source="fixture",
                        status="hit",
                    )
                ],
            )

    account = run_account(
        "12345678000190",
        providers=[
            KnownSite(),
            CompanyWebsiteProvider(
                crawler=crawler,
                site_budget=SiteCrawlBudget(max_pages=8, max_depth=2, timeout_seconds=8.0),
            ),
        ],
        infer_email=False,
    )
    assert account.extra["domain_resolution"]["canonical_domain"] == domain
    site_attempts = [item for item in account.ledger.attempts if item.provider_id == "company_website"]
    assert site_attempts
    assert site_attempts[0].documents_checked >= 1
    assert any(
        route.channel_value and "@" in route.channel_value and route.extra.get("identity_explicitly_associated")
        for route in account.routes
    )
    assert not any(
        route.channel_value == "contato@empresaexemplo.com.br" and route.extra.get("identity_explicitly_associated")
        for route in account.routes
    )


def test_cli_site_crawl_entry_writes_evidence_bundle(tmp_path: Path):
    from scripts.decision_unit_intelligence.cli import main

    out = tmp_path / "launch"
    rc = main(
        [
            "site-crawl",
            "--fixture",
            str(FIXTURE_ROOT),
            "--out",
            str(out),
            "--seed-url",
            "https://empresaexemplo.com.br/equipe",
        ]
    )
    assert rc == 0
    payload = json.loads((out / "site-crawl.json").read_text(encoding="utf-8"))
    assert payload["metrics"]["named_associated"] >= 1
    assert payload["metrics"]["false_association"] == 0
    assert payload["named_associated"]
    assert all(set(item["reason_codes"]) & STRONG_SITE_CODES for item in payload["named_associated"])
    assert not any((item.get("email") or "").startswith("contato@") for item in payload["named_associated"])
    assert payload["result"]["budget"]["pages"] <= payload["budget"]["max_pages"]


def test_no_high_value_path_reason_when_only_homepage_exists():
    crawler = MappingCrawler({"https://emptyco.com.br/": "<html><body><p>Bem-vindo à Emptyco.</p></body></html>"})
    result = run_site_contact_crawl(
        crawler=crawler,
        context=InvestigationContext(cnpj="00000000000191", legal_name="EMPTYCO"),
        canonical_domain="emptyco.com.br",
        budget=SiteCrawlBudget(max_pages=3, max_depth=1, timeout_seconds=3.0),
        rate_limit=False,
    )
    assert SITE_NO_HIGH_VALUE_PATH in result.reason_codes
    assert result.metrics["named_associated"] == 0
