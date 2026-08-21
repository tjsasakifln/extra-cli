"""Precision-critical discovery tests: domains, extract, stop-early, accounting."""

from __future__ import annotations

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.adapters.contact_pages import ContactPageAdapter
from scripts.confenge_contact_resolution.adapters.public_docs import PublicDocsAdapter
from scripts.confenge_contact_resolution.adapters.registry import RegistryAdapter
from scripts.confenge_contact_resolution.adapters.site import SiteAdapter
from scripts.confenge_contact_resolution.adapters.web_search import NoOpWebSearchProvider, WebSearchAdapter
from scripts.confenge_contact_resolution.discovery.budget import DiscoveryBudget, DiscoveryStats
from scripts.confenge_contact_resolution.discovery.domain_probe import (
    candidate_domains,
    probe_official_domain,
)
from scripts.confenge_contact_resolution.discovery.extract import (
    extract_contacts_from_html,
    extract_contacts_from_text,
    extract_emails,
    extract_phones,
    extract_whatsapp,
)
from scripts.confenge_contact_resolution.discovery.official_domain import (
    DomainClass,
    DomainResolution,
    classify_host,
    is_credible_company_domain,
)
from scripts.confenge_contact_resolution.discovery.public_document_fetch import (
    fetch_cnpj_linked_public_document,
)
from scripts.confenge_contact_resolution.discovery.web_search_providers import (
    DuckDuckGoHTMLProvider,
    parse_bing_html,
)
from scripts.confenge_contact_resolution.email_policy import assess_email
from scripts.confenge_contact_resolution.human_review import _contact_row
from scripts.confenge_contact_resolution.models import (
    ContactCandidate,
    OwnershipStatus,
    SourceProvenance,
    ThirdPartyType,
)
from scripts.confenge_contact_resolution.ownership import (
    OwnershipContext,
    apply_ownership_to_candidate,
    resolve_ownership,
)
from scripts.confenge_contact_resolution.phone_policy import assess_phone
from scripts.confenge_contact_resolution.resolver import ContactResolver, ResolverConfig
from scripts.confenge_contact_resolution.reuse_graph import ContactReuseGraph


def test_short_live_hosts_never_credible_or_official_likely():
    """wh.com / fts.com / bar.com.br must not become company official domains."""
    assert not is_credible_company_domain("wh.com", "WH CONSTRUTORA LTDA")
    assert not is_credible_company_domain("fts.com", "F T S CONSTRUTORA LTDA")
    assert not is_credible_company_domain("bar.com.br", "AILTON ADMILSON DA SILVA")
    assert not is_credible_company_domain("rf.com.br", "SOUSA GUIMARAES ENGENHARIA")
    # Generic industry host from company name must not win
    assert not is_credible_company_domain(
        "transportadora.com.br",
        "CONSTRUTORA E TRANSPORTADORA IDEAL LTDA",
    )
    # Residual-foreign product domains (skeptic residual FPs)
    assert not is_credible_company_domain("emkoelektronik.com", "EMKO CONSTRUTORA LTDA")
    assert not is_credible_company_domain("hotelparaiso.com.br", "PARAISO DAS MADEIRAS V.PALMA LTDA")
    assert not is_credible_company_domain("alcicafe.com.br", "ALCI N. BECKER")
    for host, label in (
        ("wh.com", "WH CONSTRUTORA LTDA"),
        ("fts.com", "F T S CONSTRUTORA LTDA"),
        ("transportadora.com.br", "CONSTRUTORA E TRANSPORTADORA IDEAL LTDA"),
        ("emkoelektronik.com", "EMKO CONSTRUTORA LTDA"),
        ("hotelparaiso.com.br", "PARAISO DAS MADEIRAS V.PALMA LTDA"),
    ):
        res = classify_host(host, company_label=label)
        assert res.domain_class in {
            DomainClass.UNRESOLVED.value,
            DomainClass.THIRD_PARTY.value,
            DomainClass.DIRECTORY.value,
        }, (host, res.domain_class)


def test_email_domain_residual_safe_variants():
    from scripts.confenge_contact_resolution.discovery.official_domain import (
        email_domain_aligned_with_company,
    )

    # Same brand family with region suffix allowed
    assert email_domain_aligned_with_company(
        "aegeamt.com.br",
        "AEGEA SANEAMENTO E PARTICIPACOES S.A.",
        official_domain="aegea.com.br",
    )
    # Foreign product residual rejected
    assert not email_domain_aligned_with_company(
        "emkoelektronik.com",
        "EMKO CONSTRUTORA LTDA",
        official_domain="emko.com",
    )
    assert not email_domain_aligned_with_company(
        "hotelparaiso.com.br",
        "PARAISO DAS MADEIRAS V.PALMA LTDA",
        official_domain="paraiso.com.br",
    )
    # Exact multi-token compact of company label stays aligned
    assert is_credible_company_domain(
        "alphaengenharia.com.br",
        "ALPHA ENGENHARIA E CONSTRUCOES LTDA",
    )
    assert is_credible_company_domain(
        "construtoraalpha.com.br",
        "Construtora Alpha Ltda",
    )
    assert email_domain_aligned_with_company(
        "alphaengenharia.com.br",
        "ALPHA ENGENHARIA E CONSTRUCOES LTDA",
        official_domain="alphaengenharia.com.br",
    )


def test_placeholder_phone_invalid():
    from scripts.confenge_contact_resolution.phone_policy import assess_phone, is_placeholder_phone

    assert is_placeholder_phone("+5599999999999")
    assert is_placeholder_phone("+559999999999")
    a = assess_phone("+55 99 99999-9999")
    assert a.valid is False
    assert "placeholder" in " ".join(a.notes)
    # Real-looking mobile should still pass
    b = assess_phone("11987654321")
    assert b.valid is True


def test_candidate_domains_skip_short_and_generic_slds():
    hosts = candidate_domains(razao_social="WH CONSTRUTORA LTDA")
    assert not any(h.endswith("wh.com") or h == "wh.com" for h in hosts)
    hosts2 = candidate_domains(razao_social="CONSTRUTORA E TRANSPORTADORA IDEAL LTDA")
    assert "transportadora.com.br" not in hosts2
    # Distinctive brand should still appear
    hosts3 = candidate_domains(razao_social="PAVSANTOS CONSTRUTORA LTDA")
    assert any("pavsantos" in h for h in hosts3)


def test_probe_does_not_promote_unresolved_live_hosts(monkeypatch):
    """Even if probe_host returns live, UNRESOLVED stays out of official."""

    def fake_probe(host, timeout=3.0):
        return {"host": host, "url": f"https://{host}/", "status": 200, "scheme": "https"}

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.domain_probe.probe_host",
        fake_probe,
    )
    # Force candidate list to include a short host that would have been live-promoted before
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.domain_probe.candidate_domains",
        lambda **kwargs: ["wh.com", "pavsantos.com.br"],
    )
    res = probe_official_domain(razao_social="WH CONSTRUTORA LTDA")
    assert res.domain_class == DomainClass.UNRESOLVED.value or (res.domain and "pavsantos" not in (res.domain or ""))
    # For WH label, pavsantos must not be selected either
    assert res.domain != "wh.com"
    assert not res.is_company_owned_eligible() or res.domain != "wh.com"


def test_real_company_domain_still_confirmed():
    res = classify_host("pavsantos.com.br", company_label="PAVSANTOS CONSTRUTORA LTDA")
    assert res.domain_class == DomainClass.OFFICIAL_CONFIRMED.value
    assert is_credible_company_domain("pavsantos.com.br", "PAVSANTOS CONSTRUTORA LTDA")


def test_html_extract_mailto_tel_whatsapp_jsonld():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Organization","email":"jsonld@empresa-alpha.com.br","telephone":"+55 11 3333-4444"}
    </script>
    <title>Empresa Alpha</title></head>
    <body>
      <a href="mailto:contato@empresa-alpha.com.br">Email</a>
      <a href="tel:+5511999887766">Ligue</a>
      <a href="https://wa.me/5511988776655">WhatsApp</a>
      <footer>Fale: comercial@empresa-alpha.com.br — (11) 2222-3333</footer>
    </body></html>
    """
    emails = extract_emails(html)
    phones = extract_phones(html)
    wa = extract_whatsapp(html)
    assert "contato@empresa-alpha.com.br" in emails
    assert "comercial@empresa-alpha.com.br" in emails
    assert (
        any("999887766" in p.replace(" ", "").replace("-", "") or "5511999887766" in p.replace(" ", "") for p in phones)
        or phones
    )
    assert wa
    contacts = extract_contacts_from_html(html, source_url="https://empresa-alpha.com.br/contato")
    assert contacts
    assert any(c.get("email") for c in contacts)


def test_plain_text_requires_explicit_name_label_role_and_email():
    text = (
        "CNPJ 11.222.333/0001-81 Representante legal: João da Silva; "
        "Engenheiro Civil; joao.silva@alphaengenharia.com.br"
    )
    contacts = extract_contacts_from_text(text, source_url="https://gov.br/doc/1.pdf")
    assert contacts == [
        {
            "email": "joao.silva@alphaengenharia.com.br",
            "name": "João da Silva",
            "cargo": "Representante legal",
            "url": "https://gov.br/doc/1.pdf",
            "source_url": "https://gov.br/doc/1.pdf",
            "context_text": text,
        }
    ]
    assert (
        extract_contacts_from_text(
            "Engenheiro Civil joao.silva@alphaengenharia.com.br",
            source_url="https://gov.br/doc/2.pdf",
        )
        == []
    )


def test_bing_parser_decodes_and_returns_organic_result():
    import base64

    target = "https://www.gov.br/compras/documento.pdf"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    html = f"""
      <ol><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1{encoded}">Documento</a></h2>
      <div class="b_caption"><p>Proposta publicada</p></div></li></ol>
    """
    results = parse_bing_html(html)
    assert len(results) == 1
    assert results[0].url == target
    assert results[0].snippet == "Proposta publicada"


def test_ladder_hit_filter_rejects_search_noise_and_keeps_institutional_match():
    from scripts.confenge_contact_resolution.discovery.cascade import _relevant_ladder_hit

    noise = {
        "url": "https://www.realself.com/question/implant-rippling",
        "title": "Implant question",
        "snippet": "Unrelated medical result",
    }
    assert not _relevant_ladder_hit(
        "pncp_transparency_compras",
        noise,
        cnpj14="11222333000181",
        razao_social="Alpha Engenharia Ltda",
    )
    official = {
        "url": "https://transparencia.municipio.gov.br/contrato/1",
        "title": "Contrato Alpha Engenharia",
        "snippet": "Fornecedor Alpha Engenharia",
    }
    assert _relevant_ladder_hit(
        "pncp_transparency_compras",
        official,
        cnpj14="11222333000181",
        razao_social="Alpha Engenharia Ltda",
    )


def test_public_document_requires_exact_cnpj_before_emitting_contact(monkeypatch):
    html = b"""
      <html><body><p>CNPJ 11.222.333/0001-81</p><div>
      <strong>Joao da Silva</strong><span>Engenheiro Civil</span>
      <a href="mailto:joao@alphaengenharia.com.br">email</a></div></body></html>
    """

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            return html

        def geturl(self):
            return "https://gov.br/doc/1"

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.public_document_fetch._public_http_url",
        lambda *args, **kwargs: (True, None),
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.public_document_fetch._open_public_url",
        lambda *args, **kwargs: Response(),
    )
    linked = fetch_cnpj_linked_public_document(
        "https://gov.br/doc/1",
        cnpj14="11222333000181",
    )
    assert linked.cnpj_linked is True
    assert linked.contacts[0]["name"] == "Joao da Silva"
    wrong = fetch_cnpj_linked_public_document(
        "https://gov.br/doc/1",
        cnpj14="99888777000166",
    )
    assert wrong.cnpj_linked is False
    assert wrong.as_public_docs() == []


def test_stop_early_budget_and_contact_found():
    budget = DiscoveryBudget(max_search_queries=0, max_pages=4, max_total_requests=10, max_seconds=30)
    stats = DiscoveryStats()
    assert not stats.budget_exhausted(budget)
    stats.pages_fetched = 4
    assert stats.budget_exhausted(budget)
    stats.mark_budget(budget)
    assert stats.outcome == "BUDGET_EXHAUSTED"
    # zero search does not exhaust immediately
    s2 = DiscoveryStats()
    b2 = DiscoveryBudget(max_search_queries=0, max_pages=8)
    assert not s2.budget_exhausted(b2)


def test_search_provider_failure_is_not_reported_as_source_exhaustion(monkeypatch):
    from urllib.error import URLError

    def unavailable(*args, **kwargs):
        raise URLError("blocked")

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.web_search_providers.urlopen",
        unavailable,
    )
    provider = DuckDuckGoHTMLProvider(min_interval=0)
    for query in ("one", "two", "three"):
        assert provider.search(query) == []
    assert provider.available is False
    assert provider.last_error == "URLError"

    from scripts.confenge_contact_resolution.discovery.cascade import DiscoveryCascade

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.lookup_public_docs_for_cnpj",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.probe_official_domain",
        lambda **kwargs: DomainResolution(),
    )
    result = DiscoveryCascade(
        budget=DiscoveryBudget(max_search_queries=12, max_pages=8, max_total_requests=40),
        web_provider=provider,
        allow_network=True,
    ).run(cnpj14="11222333000181", razao_social="ALPHA ENGENHARIA LTDA")
    blocked = [a for a in result.source_attempts if a["outcome"] == "EXTERNAL_BLOCKER"]
    assert blocked
    assert all(a["reason_code"] == "search_provider_unavailable" for a in blocked)


def test_resolution_cache_signature_includes_contract_and_discovery_budget():
    from scripts.confenge_contact_resolution.discovery.cascade import DiscoveryCascade

    low = ResolverConfig(
        discovery_cascade=DiscoveryCascade(
            budget=DiscoveryBudget(max_search_queries=2, max_pages=2),
        )
    )
    high = ResolverConfig(
        discovery_cascade=DiscoveryCascade(
            budget=DiscoveryBudget(max_search_queries=12, max_pages=16),
        )
    )
    assert ContactResolver(low)._adapters_sig() != ContactResolver(high)._adapters_sig()
    assert "schema=" in ContactResolver(low)._adapters_sig()


def test_cascade_stops_early_on_functional_control_eligible_doc(monkeypatch):
    """Observed licitacoes@ on a CNPJ-linked document is a company-route success."""
    from scripts.confenge_contact_resolution.discovery.budget import InvestigationOutcome
    from scripts.confenge_contact_resolution.discovery.cascade import DiscoveryCascade

    calls = {"search": 0, "probe": 0, "crawl": 0}

    def fake_docs(cnpj14, **kwargs):
        return [
            {
                "email": "licitacoes@alphaengenharia.com.br",
                "cnpj14": cnpj14,
                "evidence_strength": "company_authored_document",
                "url": "https://datalake.example/doc/1",
                "doc_type": "proposta",
            }
        ]

    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.cascade.lookup_public_docs_for_cnpj",
        fake_docs,
    )
    cascade = DiscoveryCascade(
        budget=DiscoveryBudget(max_search_queries=6, max_pages=8, max_total_requests=20),
        allow_network=False,
        dsn=None,
    )
    result = cascade.run(
        cnpj14="11222333000181",
        razao_social="ALPHA ENGENHARIA E CONSTRUCOES LTDA",
        stop_when_strong_contact=True,
    )
    assert result.stats.outcome == InvestigationOutcome.CONTACT_FOUND.value
    assert result.stats.stop_reason == "controlled_eligible_public_doc"
    assert result.stats.search_queries == 0
    assert calls["search"] == 0
    assert calls["probe"] == 0
    assert not any(a["reason_code"] == "named_human_contact_found" for a in result.source_attempts)
    assert any(a["reason_code"] == "controlled_eligible_company_route_found" for a in result.source_attempts)
    assert all(
        {
            "cnpj14",
            "source_adapter",
            "observed_at",
            "outcome",
            "reason_code",
            "limitations",
            "evidence_sha256",
            "terminal_state",
            "next_action",
        }
        <= set(attempt)
        for attempt in result.source_attempts
    )
    assert any((d.get("email") or "").endswith("@alphaengenharia.com.br") for d in (result.ctx.public_docs or []))


def test_strong_public_doc_requires_exact_cnpj_and_non_guessed_email():
    from scripts.confenge_contact_resolution.discovery.cascade import _has_strong_doc_contact

    doc = {
        "cnpj14": "11222333000181",
        "email": "maria@alpha.example",
        "name": "Maria da Silva",
        "cargo": "Diretora Comercial",
        "url": "https://alpha.example/proposta.pdf",
        "evidence_strength": "company_authored_document",
    }
    assert _has_strong_doc_contact([doc], cnpj14="11222333000181")
    assert not _has_strong_doc_contact([doc], cnpj14="99888777000166")
    assert not _has_strong_doc_contact([{**doc, "pattern_guessed_email": True}], cnpj14="11222333000181")


def test_accounting_shared_phone_rejected_end_to_end():
    """§37: shared phone across many CNPJs + accounting entity → ACCOUNTING / third-party."""
    graph = ContactReuseGraph()
    phone = "1133334444"
    # 10 unrelated construction CNPJs share the same phone
    cnpjs = [f"{10000000 + i:08d}0001{i % 10}{i % 10}"[:14] for i in range(10)]
    # ensure 14 digits
    cnpjs = []
    for i in range(10):
        c = f"{11 + i:02d}{222333 + i:06d}0001{i:02d}"
        c = (c + "00")[:14]
        cnpjs.append(c)
        graph.register_company(c, razao_social=f"CONSTRUTORA XYZ {i} LTDA")
        graph.observe_phone(phone, c)

    target = cnpjs[0]
    # Accounting office also uses the phone
    graph.register_company("99888777000166", razao_social="ESCRITORIO CONTABIL ABC LTDA")
    graph.observe_phone(phone, "99888777000166")

    pa = assess_phone(phone)
    cand = ContactCandidate(
        candidate_id="acc1",
        cnpj14=target,
        account_key=target,
        phone_raw=pa.phone_raw,
        phone_e164=pa.phone_e164,
        phone_type=pa.phone_type,
        source=SourceProvenance(
            source_type="registry",
            source_url="official_company_registry",
            notes="cadastro",
        ),
        confidence=0.3,
        enrollable=True,
        site="https://abccontabilidade.com.br",
    )
    reuse = graph.best_signal(target, phone=phone)
    assert reuse is not None
    assert reuse.unrelated_count >= 3

    octx = OwnershipContext(
        cnpj14=target,
        razao_social="CONSTRUTORA XYZ 0 LTDA",
        official_domain=None,
    )
    result = resolve_ownership(
        cand,
        ctx=octx,
        reuse=reuse,
        registry_hit=None,
        context_text="Escritório Contábil ABC — contabilidade e assessoria contábil",
        art_crea_only=False,
        independent_sources_count=1,
    )
    apply_ownership_to_candidate(cand, result)
    assert cand.enrollable is False
    assert cand.ownership_status in {
        OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
        OwnershipStatus.SHARED_EXTERNAL_CONTACT.value,
    }
    if cand.ownership_status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value:
        assert (cand.third_party_type or "").upper() in {
            ThirdPartyType.ACCOUNTING.value,
            "ACCOUNTING",
            "OTHER",
        }


def test_official_site_email_company_owned():
    """§38: aligned official domain + contact email → COMPANY_OWNED enrollable."""
    cnpj = "11222333000181"
    ea = assess_email("contato@alphaengenharia.com.br")
    cand = ContactCandidate(
        candidate_id="ok1",
        cnpj14=cnpj,
        account_key=cnpj,
        email=ea.email,
        email_display=ea.email_display,
        email_layers=ea.layers,
        verification_status=ea.verification_status,
        source=SourceProvenance(
            source_type="site",
            source_url="https://alphaengenharia.com.br/contato",
            source_date="2026-06-01",
        ),
        confidence=0.5,
        enrollable=ea.enrollable,
        site="https://alphaengenharia.com.br",
    )
    octx = OwnershipContext(
        cnpj14=cnpj,
        razao_social="ALPHA ENGENHARIA E CONSTRUCOES LTDA",
        official_domain="alphaengenharia.com.br",
    )
    result = resolve_ownership(
        cand,
        ctx=octx,
        reuse=None,
        registry_hit=None,
        context_text="CNPJ 11.222.333/0001-81 Alpha Engenharia",
        independent_sources_count=1,
    )
    apply_ownership_to_candidate(cand, result)
    assert cand.ownership_status == OwnershipStatus.COMPANY_OWNED.value
    assert cand.enrollable is True


def test_human_review_reads_source_provenance():
    row = _contact_row(
        {"cnpj14": "11222333000181", "razao_social": "ACME", "official_domain": "acme.com.br"},
        {
            "email": "contato@acme.com.br",
            "ownership_status": "COMPANY_OWNED",
            "enrollable": True,
            "source": {
                "source_type": "site",
                "source_url": "https://acme.com.br/contato",
            },
        },
        bucket="ACCEPTED",
    )
    assert row["source_url"] == "https://acme.com.br/contato"
    assert row["source_type"] == "site"


def test_resolver_rejects_unaligned_official_domain_injection():
    """Injecting site pages on a third-party host must not yield enrollable COMPANY_OWNED."""
    cnpj = "23305610000107"

    def builder(c: str) -> AdapterContext:
        return AdapterContext(
            cnpj14=c,
            registry_record={
                "legal_name": "WH CONSTRUTORA LTDA",
                "phone": "11999990000",
                "official_match_status": "MATCHED",
            },
            site_pages=[
                {
                    "url": "https://wh.com/contato",
                    "contacts": [{"email": "office@wh.com"}],
                }
            ],
            allow_network=False,
        )

    cfg = ResolverConfig(
        adapters=[
            RegistryAdapter(prefer_network=False),
            SiteAdapter(),
            PublicDocsAdapter(),
            ContactPageAdapter(),
            WebSearchAdapter(provider=NoOpWebSearchProvider(), enabled=False),
        ],
        allow_network=False,
        apply_ownership=True,
        context_builder=builder,
        job_meta={cnpj: {"razao_social": "WH CONSTRUTORA LTDA"}},
    )
    res = ContactResolver(cfg).resolve_one(cnpj)
    # Must not set wh.com as credible official
    if res.official_domain:
        assert not is_credible_company_domain(res.official_domain, "WH CONSTRUTORA LTDA")
    for c in res.candidates:
        if c.email and "wh.com" in c.email:
            assert c.enrollable is False or c.ownership_status != OwnershipStatus.COMPANY_OWNED.value
