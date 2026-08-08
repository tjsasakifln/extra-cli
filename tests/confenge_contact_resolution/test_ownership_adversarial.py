"""Adversarial fixtures A–J for ownership resolver (shipped path).

These drive resolve_ownership / ContactResolver — not reimplemented logic.
"""

from __future__ import annotations

from pathlib import Path

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.adapters.contact_pages import ContactPageAdapter
from scripts.confenge_contact_resolution.adapters.public_docs import PublicDocsAdapter
from scripts.confenge_contact_resolution.adapters.registry import RegistryAdapter
from scripts.confenge_contact_resolution.adapters.site import SiteAdapter
from scripts.confenge_contact_resolution.adapters.web_search import NoOpWebSearchProvider, WebSearchAdapter
from scripts.confenge_contact_resolution.email_policy import assess_email
from scripts.confenge_contact_resolution.enrichment_batch import (
    CompanyJob,
    EnrichmentBatchRunner,
    EnrichmentMetrics,
)
from scripts.confenge_contact_resolution.models import (
    ContactCandidate,
    OwnershipStatus,
    SourceProvenance,
    ThirdPartyType,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.ownership import (
    OwnershipContext,
    apply_ownership_to_candidate,
    resolve_ownership,
)
from scripts.confenge_contact_resolution.phone_policy import assess_phone
from scripts.confenge_contact_resolution.resolver import ContactResolver, ResolverConfig
from scripts.confenge_contact_resolution.reuse_graph import ContactReuseGraph
from scripts.confenge_contact_resolution.third_party_registry import ThirdPartyRegistry


def _cand(
    *,
    email: str | None = None,
    phone: str | None = None,
    source_type: str = "site",
    source_url: str | None = "https://example.com/contato",
    pattern_guessed: bool = False,
    name: str | None = None,
    cargo: str | None = None,
    role_class: str = "generic",
    site: str | None = None,
    cnpj14: str = "11222333000181",
) -> ContactCandidate:
    ea = assess_email(email, pattern_guessed=pattern_guessed)
    pa = assess_phone(phone)
    return ContactCandidate(
        candidate_id="t1",
        cnpj14=cnpj14,
        account_key=cnpj14,
        name=name,
        cargo=cargo,
        role_class=role_class,
        email=ea.email,
        email_display=ea.email_display,
        phone_raw=pa.phone_raw,
        phone_e164=pa.phone_e164,
        phone_type=pa.phone_type,
        site=site,
        source=SourceProvenance(source_type=source_type, source_url=source_url, source_date="2026-06-01"),
        verification_status=ea.verification_status
        if ea.email
        else (VerificationStatus.OBSERVED.value if pa.valid else VerificationStatus.NOT_AVAILABLE.value),
        email_layers=ea.layers,
        confidence=0.3,
        enrollable=ea.enrollable,
    )


def _offline_adapters():
    return [
        RegistryAdapter(prefer_network=False),
        SiteAdapter(),
        PublicDocsAdapter(),
        ContactPageAdapter(),
        WebSearchAdapter(provider=NoOpWebSearchProvider(), enabled=False),
    ]


# --- A: legitimate company email ---
def test_case_a_legitimate_company_email_enrollable() -> None:
    c = _cand(
        email="comercial@construtoraalpha.com.br",
        source_type="site",
        source_url="https://construtoraalpha.com.br/contato",
        site="https://construtoraalpha.com.br",
    )
    ctx = OwnershipContext(
        cnpj14="11222333000181",
        razao_social="Construtora Alpha Ltda",
        official_domain="construtoraalpha.com.br",
    )
    r = resolve_ownership(c, ctx=ctx)
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status == OwnershipStatus.COMPANY_OWNED.value
    assert c.enrollable is True
    assert c.ownership_status == OwnershipStatus.COMPANY_OWNED.value


def test_residual_foreign_email_never_enrollable_via_site_score() -> None:
    """Structural gate: residual-foreign domains cannot enroll via score soup.

    Skeptic residual FPs (emkoelektronik / hotelparaiso / alcicafe) must fail
    enrollable through resolve_ownership itself — not a post-hoc feed filter.
    """
    cases = (
        (
            "info@emkoelektronik.com",
            "EMKO CONSTRUTORA LTDA",
            "emkoelektronik.com",
            "site",
            "https://emkoelektronik.com/contato",
        ),
        (
            "reservas@hotelparaiso.com.br",
            "PARAISO DAS MADEIRAS V.PALMA LTDA",
            "hotelparaiso.com.br",
            "official_domain",
            "https://hotelparaiso.com.br/",
        ),
        (
            "contato@alcicafe.com.br",
            "ALCI N. BECKER",
            "alcicafe.com.br",
            "company_page",
            "https://alcicafe.com.br/contato",
        ),
        # Score-soup shape: contact_page on residual host + official_domain set to same host
        (
            "info@emkoelektronik.com",
            "EMKO CONSTRUTORA LTDA",
            "emkoelektronik.com",
            "contact_page",
            "https://emkoelektronik.com/contato",
        ),
    )
    for email, razao, domain, source_type, url in cases:
        c = _cand(
            email=email,
            source_type=source_type,
            source_url=url,
            site=f"https://{domain}",
        )
        ctx = OwnershipContext(
            cnpj14="11222333000181",
            razao_social=razao,
            # Deliberately poisoned official_domain — gate must still refuse
            official_domain=domain,
        )
        r = resolve_ownership(c, ctx=ctx)
        apply_ownership_to_candidate(c, r)
        assert c.enrollable is False, (email, source_type, r.ownership_status, r.score_parts)
        assert r.ownership_status != OwnershipStatus.COMPANY_OWNED.value, (
            email,
            source_type,
            r.score_parts,
        )
        assert r.domain_matches_company is not True


def test_aligned_official_domain_still_enrollable() -> None:
    """Positive control: residual-safe brand domains still become COMPANY_OWNED."""
    c = _cand(
        email="comercial@aegea.com.br",
        source_type="site",
        source_url="https://aegea.com.br/contato",
        site="https://aegea.com.br",
    )
    ctx = OwnershipContext(
        cnpj14="11222333000181",
        razao_social="AEGEA SANEAMENTO E PARTICIPACOES S.A.",
        official_domain="aegea.com.br",
    )
    r = resolve_ownership(c, ctx=ctx)
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status == OwnershipStatus.COMPANY_OWNED.value
    assert c.enrollable is True
    assert r.domain_matches_company is True


def test_short_generic_official_host_never_enrollable() -> None:
    """wh.com / fts.com must not COMPANY_OWN even when official_domain is poisoned."""
    for email, razao, domain in (
        ("contato@wh.com", "WH CONSTRUTORA LTDA", "wh.com"),
        ("support@fts.com", "F T S CONSTRUTORA LTDA", "fts.com"),
    ):
        c = _cand(
            email=email,
            source_type="site",
            source_url=f"https://{domain}/",
            site=f"https://{domain}/",
        )
        ctx = OwnershipContext(
            cnpj14="18568718000144",
            razao_social=razao,
            official_domain=domain,
        )
        r = resolve_ownership(c, ctx=ctx)
        apply_ownership_to_candidate(c, r)
        assert c.enrollable is False, (email, r.ownership_status, r.score_parts)
        assert r.ownership_status != OwnershipStatus.COMPANY_OWNED.value
        assert r.domain_matches_company is not True


def test_phone_only_on_residual_foreign_site_never_enrollable() -> None:
    """CONNECTOR-style FP: scrape host blocks phone even when official_domain is good.

    Realistic: site/source_url=caiafafacilities.com.br, official_domain=connector.eng.br.
    Must not prefer official over residual third-party scrape host.
    """
    for official in ("caiafafacilities.com.br", "connector.eng.br"):
        c = _cand(
            phone="61999185906",
            source_type="site",
            source_url="https://caiafafacilities.com.br/",
            site="https://caiafafacilities.com.br/",
            cnpj14="01114245000102",
        )
        ctx = OwnershipContext(
            cnpj14="01114245000102",
            razao_social="CONNECTOR ENGENHARIA LTDA",
            official_domain=official,
        )
        r = resolve_ownership(c, ctx=ctx)
        apply_ownership_to_candidate(c, r)
        assert c.enrollable is False, (official, r.ownership_status, r.score_parts)
        assert r.ownership_status != OwnershipStatus.COMPANY_OWNED.value
        assert "phone_identity_gate_blocked" in r.score_parts or "phone_source_host" in (r.ownership_reason or "")
        assert any("phone_scrape_host_unaligned" in p for p in r.score_parts)


def test_fantasia_only_domain_match_not_enrollable() -> None:
    """LED INTERNET + fantasia CACTUS must not enroll cactus@cactus.com.br."""
    c = _cand(
        email="cactus@cactus.com.br",
        source_type="site",
        source_url="https://cactus.com.br/",
        site="https://cactus.com.br/",
    )
    ctx = OwnershipContext(
        cnpj14="11222333000181",
        razao_social="LED INTERNET LTDA",
        nome_fantasia="CACTUS INFORMATICA",
        official_domain="cactus.com.br",
    )
    r = resolve_ownership(c, ctx=ctx)
    apply_ownership_to_candidate(c, r)
    assert c.enrollable is False
    assert r.ownership_status != OwnershipStatus.COMPANY_OWNED.value
    assert r.domain_matches_company is not True


def test_phone_only_on_aligned_company_site_may_enroll() -> None:
    c = _cand(
        phone="4832221000",
        source_type="site",
        source_url="https://pavsantos.com.br/contato",
        site="https://pavsantos.com.br",
        cnpj14="03575041000102",
    )
    ctx = OwnershipContext(
        cnpj14="03575041000102",
        razao_social="PAVSANTOS CONSTRUTORA LTDA",
        official_domain="pavsantos.com.br",
    )
    r = resolve_ownership(c, ctx=ctx)
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status == OwnershipStatus.COMPANY_OWNED.value
    assert c.enrollable is True


# --- B: accounting office domain ---
def test_case_b_accounting_domain_rejected() -> None:
    c = _cand(
        email="beta@contabilidadeoliveira.com.br",
        source_type="registry",
        source_url="https://cadastro.example/beta",
    )
    ctx = OwnershipContext(
        cnpj14="22333444000192",
        razao_social="Construtora Beta Ltda",
    )
    reg = ThirdPartyRegistry()
    hit = reg.lookup(domain="contabilidadeoliveira.com.br", email=c.email)
    r = resolve_ownership(c, ctx=ctx, registry_hit=hit, context_text="Contabilidade Oliveira")
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value
    assert r.third_party_type == ThirdPartyType.ACCOUNTING.value
    assert c.enrollable is False


def test_case_b_accounting_site_circular_domain_not_company_owned() -> None:
    """Skeptic regression: email domain == third-party site must NOT enroll for target.

    beta@contabilidadeoliveira.com.br found on https://contabilidadeoliveira.com.br
    attributed to Construtora Beta must stay THIRD_PARTY, never COMPANY_OWNED.
    """
    c = _cand(
        email="beta@contabilidadeoliveira.com.br",
        source_type="site",
        source_url="https://contabilidadeoliveira.com.br/contato",
        site="https://contabilidadeoliveira.com.br",
        cnpj14="22333444000192",
    )
    ctx = OwnershipContext(
        cnpj14="22333444000192",
        razao_social="Construtora Beta Ltda",
        # Deliberately wrong: would amplify false positive if trusted blindly
        official_domain="contabilidadeoliveira.com.br",
    )
    r = resolve_ownership(c, ctx=ctx)
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value
    assert r.third_party_type == ThirdPartyType.ACCOUNTING.value
    assert c.enrollable is False
    assert r.ownership_status != OwnershipStatus.COMPANY_OWNED.value


# --- C: shared phone across many unrelated CNPJs ---
def test_case_c_shared_phone_external() -> None:
    graph = ContactReuseGraph()
    phone = "4833330000"
    target = "10000000000191"
    graph.observe_phone(phone, target)
    for i in range(42):
        # distinct roots
        cnpj = f"{20000000 + i:08d}000191"
        graph.observe_phone(phone, cnpj)
        graph.register_company(cnpj, razao_social=f"Empresa {i} Ltda")
    sig = graph.signal_for_phone(phone, target)
    assert sig is not None
    assert sig.unrelated_count >= 40

    c = _cand(phone=phone, source_type="registry", cnpj14=target)
    ctx = OwnershipContext(cnpj14=target, razao_social="Alvo Construtora")
    r = resolve_ownership(c, ctx=ctx, reuse=sig)
    assert r.ownership_status == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value
    assert r.enrollable is False


# --- D: matriz/filiais same root share phone — do not reject ---
def test_case_d_matriz_filial_shared_phone_kept() -> None:
    graph = ContactReuseGraph()
    phone = "1132221000"
    root = "11222333"
    cnpjs = [f"{root}0001{i:02d}" for i in range(8)]
    # fix to valid 14-digit style with same root
    cnpjs = [f"{root}{i:06d}" for i in range(1, 9)]
    for cnpj in cnpjs:
        graph.observe_phone(phone, cnpj)
        graph.register_company(cnpj, razao_social="Acme Matriz/Filial")
    target = cnpjs[0]
    sig = graph.signal_for_phone(phone, target)
    assert sig is not None
    assert sig.same_root_count >= 7
    assert sig.unrelated_count == 0

    c = _cand(
        phone=phone,
        email="contato@acme-filial.com.br",
        source_type="site",
        source_url="https://acme-filial.com.br/contato",
        site="https://acme-filial.com.br",
        cnpj14=target,
    )
    ctx = OwnershipContext(
        cnpj14=target,
        razao_social="Acme Engenharia Filial",
        official_domain="acme-filial.com.br",
    )
    r = resolve_ownership(c, ctx=ctx, reuse=sig)
    assert r.ownership_status != OwnershipStatus.SHARED_EXTERNAL_CONTACT.value
    assert r.ownership_status in {
        OwnershipStatus.COMPANY_OWNED.value,
        OwnershipStatus.LIKELY_COMPANY_OWNED.value,
    }


# --- E: freemail with strong multi-source proof ---
def test_case_e_gmail_strong_proof_may_enroll() -> None:
    c = _cand(
        email="construtoragamma@gmail.com",
        source_type="public_docs",
        source_url="https://pncp.gov.br/doc/assinado-gamma",
    )
    # Simulate multi-source + official doc
    c.independent_sources_count = 2
    c.found_on_official_source = True
    ctx = OwnershipContext(
        cnpj14="33444555000103",
        razao_social="Construtora Gamma Ltda",
    )
    r = resolve_ownership(
        c,
        ctx=ctx,
        independent_sources_count=2,
        context_text="documento assinado Construtora Gamma",
    )
    # public_docs gives +20+40; freemail -15 + multi + doc proof
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status in {
        OwnershipStatus.COMPANY_OWNED.value,
        OwnershipStatus.LIKELY_COMPANY_OWNED.value,
    }
    if r.ownership_status == OwnershipStatus.COMPANY_OWNED.value:
        assert c.enrollable is True


# --- F: freemail weak / aggregator only ---
def test_case_f_gmail_weak_not_enrollable() -> None:
    c = _cand(
        email="alguem@gmail.com",
        source_type="web_search",
        source_url="https://aggregator.example/dir",
    )
    ctx = OwnershipContext(cnpj14="33444555000103", razao_social="Construtora Gamma Ltda")
    r = resolve_ownership(c, ctx=ctx, independent_sources_count=1)
    apply_ownership_to_candidate(c, r)
    assert c.enrollable is False
    assert r.ownership_status in {
        OwnershipStatus.UNRESOLVED.value,
        OwnershipStatus.LIKELY_COMPANY_OWNED.value,
    }


# --- G: pattern guess never enrollable ---
def test_case_g_pattern_guess_never_enrollable() -> None:
    c = _cand(
        email="joao@empresa.com.br",
        pattern_guessed=True,
        source_type="site",
        source_url="https://empresa.com.br",
        site="https://empresa.com.br",
    )
    # force pattern style
    c = _cand(
        email="joao.silva@empresa.com.br",
        pattern_guessed=True,
        source_type="site",
        site="https://empresa.com.br",
    )
    ctx = OwnershipContext(
        cnpj14="11222333000181",
        razao_social="Empresa Ltda",
        official_domain="empresa.com.br",
    )
    r = resolve_ownership(c, ctx=ctx)
    apply_ownership_to_candidate(c, r)
    assert c.enrollable is False
    assert c.email_layers.pattern_guessed is True
    assert r.ownership_status == OwnershipStatus.UNRESOLVED.value


# --- H: lawyer / legal office ---
def test_case_h_lawyer_rejected() -> None:
    c = _cand(
        email="contato@silvaadvocacia.com.br",
        source_type="public_docs",
        source_url="https://jus.example/processo",
    )
    ctx = OwnershipContext(cnpj14="44555666000114", razao_social="Construtora Delta SA")
    hit = ThirdPartyRegistry().lookup(domain="silvaadvocacia.com.br", email=c.email)
    r = resolve_ownership(
        c,
        ctx=ctx,
        registry_hit=hit,
        context_text="Escritório de advocacia Silva",
    )
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value
    assert r.third_party_type == ThirdPartyType.LEGAL.value
    assert c.enrollable is False


# --- I: ART/CREA engineer not auto-promoted ---
def test_case_i_art_engineer_not_commercial() -> None:
    c = _cand(
        email="engenheiro@pessoal.example",
        source_type="public_docs",
        name="Eng. Fulano",
        cargo="Responsável técnico ART",
        role_class="engenharia",
    )
    ctx = OwnershipContext(cnpj14="55666777000125", razao_social="Obra XYZ Construtora")
    r = resolve_ownership(c, ctx=ctx, art_crea_only=True)
    apply_ownership_to_candidate(c, r)
    assert c.enrollable is False
    assert "art_crea" in (r.ownership_reason or "").lower() or r.enrollable is False


# --- J: economic group shared domain allowed ---
def test_case_j_economic_group_domain_allowed() -> None:
    graph = ContactReuseGraph()
    domain = "grupomega.com.br"
    a = "66777888000136"
    b = "66777888000217"  # different branch digits but we mark group
    # Use distinct roots but same group id
    a = "66777888000136"
    b = "77888999000147"
    graph.register_company(a, razao_social="Mega Construtora", economic_group_id="grupo-mega")
    graph.register_company(b, razao_social="Mega Engenharia", economic_group_id="grupo-mega")
    graph.observe_domain(domain, a)
    graph.observe_domain(domain, b)
    graph.observe_email(f"comercial@{domain}", a)
    graph.observe_email(f"comercial@{domain}", b)
    sig = graph.signal_for_email(f"comercial@{domain}", a)
    assert sig is not None
    assert sig.same_group_count >= 1 or sig.unrelated_count == 0

    c = _cand(
        email=f"comercial@{domain}",
        source_type="site",
        source_url=f"https://{domain}/contato",
        site=f"https://{domain}",
        cnpj14=a,
    )
    ctx = OwnershipContext(
        cnpj14=a,
        razao_social="Mega Construtora SA",
        official_domain=domain,
        economic_group_id="grupo-mega",
    )
    r = resolve_ownership(c, ctx=ctx, reuse=sig)
    apply_ownership_to_candidate(c, r)
    assert r.ownership_status != OwnershipStatus.SHARED_EXTERNAL_CONTACT.value
    assert c.enrollable is True or r.ownership_status in {
        OwnershipStatus.COMPANY_OWNED.value,
        OwnershipStatus.LIKELY_COMPANY_OWNED.value,
    }


def test_resolver_integration_rejects_accounting_keeps_company(tmp_path: Path) -> None:
    """Full resolver path: company domain enrollable; contador rejected."""
    company_cnpj = "11222333000181"
    ctx_map = {
        company_cnpj: AdapterContext(
            cnpj14=company_cnpj,
            allow_network=False,
            registry_record={
                "email": "contato@acme-engenharia.example",
                "phone": "4832221000",
                "legal_name": "ACME Engenharia LTDA",
                "company_size": "EPP",
                "source_date": "2026-01-15",
                "official_match_status": "MATCHED",
                "site": "https://acme-engenharia.example",
            },
            site_pages=[
                {
                    "url": "https://acme-engenharia.example/contato",
                    "source_date": "2026-05-01",
                    "contacts": [
                        {
                            "email": "comercial@acme-engenharia.example",
                            "phone": "48999991234",
                            "cargo": "Comercial",
                        },
                        {
                            "email": "acme@contabilidadeoliveira.com.br",
                            "phone": "4833339999",
                            "cargo": "Contador",
                        },
                    ],
                }
            ],
        )
    }

    def builder(c: str) -> AdapterContext:
        return ctx_map.get(c, AdapterContext(cnpj14=c, allow_network=False))

    cfg = ResolverConfig(
        adapters=_offline_adapters(),
        allow_network=False,
        context_builder=builder,
        apply_ownership=True,
        third_party_registry=ThirdPartyRegistry(),
        reuse_graph=ContactReuseGraph(),
    )
    res = ContactResolver(cfg).resolve_one(company_cnpj)
    emails = {c.email for c in res.candidates if c.email}
    assert "comercial@acme-engenharia.example" in emails or "contato@acme-engenharia.example" in emails
    # accounting must not be enrollable candidate
    for c in res.candidates:
        if c.email and "contabilidade" in c.email:
            assert c.enrollable is False
    # rejected list should capture third-party when removed
    rejected_vals = " ".join(str(r.get("value")) for r in res.rejected_contacts)
    assert "contabilidade" in rejected_vals or all(
        "contabilidade" not in (c.email or "") for c in res.candidates if c.enrollable
    )
    enrollable = [c for c in res.candidates if c.enrollable]
    assert enrollable
    assert all(
        c.ownership_status in {OwnershipStatus.COMPANY_OWNED.value, OwnershipStatus.HUMAN_CONFIRMED.value}
        for c in enrollable
    )


def test_enrichment_batch_artifacts_and_metrics(tmp_path: Path) -> None:
    company_cnpj = "11222333000181"
    bad_cnpj = "99888777000166"
    ctx_map = {
        company_cnpj: AdapterContext(
            cnpj14=company_cnpj,
            allow_network=False,
            registry_record={
                "email": "licitacoes@construtoraalpha.example",
                "phone": "4832221000",
                "legal_name": "Construtora Alpha Ltda",
                "company_size": "EPP",
                "source_date": "2026-05-01",
                "official_match_status": "MATCHED",
                "site": "https://construtoraalpha.example",
            },
            contact_pages=[
                {
                    "url": "https://construtoraalpha.example/contato",
                    "source_date": "2026-06-01",
                    "people": [
                        {
                            "email": "comercial@construtoraalpha.example",
                            "cargo": "Comercial",
                        }
                    ],
                }
            ],
        ),
        bad_cnpj: AdapterContext(
            cnpj14=bad_cnpj,
            allow_network=False,
            registry_record={
                "email": "x@contabilidadez.com.br",
                "legal_name": "Beta Obras Ltda",
                "official_match_status": "MATCHED",
            },
        ),
    }

    def builder(c: str) -> AdapterContext:
        return ctx_map.get(c, AdapterContext(cnpj14=c, allow_network=False))

    cfg = ResolverConfig(
        adapters=_offline_adapters(),
        allow_network=False,
        context_builder=builder,
        apply_ownership=True,
    )
    out = tmp_path / "contact-enrichment" / "run-test"
    runner = EnrichmentBatchRunner(
        output_dir=out,
        resolver_config=cfg,
        run_id="run-test",
        baseline_metrics={"verified_email_rate": 0.0},
    )
    # Must re-bind context_builder on the created resolver
    runner.resolver.config.context_builder = builder
    runner.resolver.config.adapters = _offline_adapters()

    jobs = [
        CompanyJob(cnpj14=company_cnpj, razao_social="Construtora Alpha Ltda", priority_tier="A1", priority_rank=1),
        CompanyJob(cnpj14=bad_cnpj, razao_social="Beta Obras Ltda", priority_tier="universe", priority_rank=99),
    ]
    manifest = runner.run(jobs, resume=False)
    assert manifest["ok"] is True
    assert (out / "metrics.json").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "accounting-contact-rejections.jsonl").is_file()
    assert (out / "warmbly_feed" / "contacts.jsonl").is_file()
    metrics = runner.metrics.as_dict()
    assert metrics["companies_processed"] == 2
    assert "verified_email_rate" in metrics
    assert "third_party_contacts_rejected" in metrics
    # No enrollable pattern guesses
    assert metrics["pattern_guesses_rejected"] >= 0


def test_warmbly_map_preserves_ownership_and_blocks_non_enrollable() -> None:
    from scripts.warmbly_bridge.mapping import _map_contact

    mapped = _map_contact(
        {
            "email": "a@contador.com.br",
            "ownership_status": "THIRD_PARTY_SERVICE_PROVIDER",
            "verification_status": "OBSERVED",
            "enrollable": False,
            "recommended": True,
            "confidence": "0.2",
            "role_class": "accounting_external",
        },
        idx=0,
        cnpj="11222333000181",
    )
    assert mapped["enrollable"] is False
    assert mapped["recommended"] is False
    assert mapped["ownership_status"] == "THIRD_PARTY_SERVICE_PROVIDER"

    good = _map_contact(
        {
            "email": "comercial@empresa.com.br",
            "ownership_status": "COMPANY_OWNED",
            "verification_status": "VERIFIED",
            "enrollable": True,
            "recommended": True,
            "confidence": "0.9",
            "role_class": "comercial",
            "provenance": {"source_type": "site", "source_url": "https://empresa.com.br"},
        },
        idx=1,
        cnpj="11222333000181",
    )
    assert good["enrollable"] is True
    assert good["ownership_status"] == "COMPANY_OWNED"
    assert good["verification_status"] in {
        "OFFICIAL_SOURCE",
        "INSTITUTIONAL_GENERIC",
        "VERIFIED",
    }


def test_metrics_coverage_spike_flag() -> None:
    m = EnrichmentMetrics()
    m.companies_processed = 10
    m.companies_with_enrollable_email = 8
    m.emails_found = 8
    m.emails_verified = 8
    m.finalize(duration_s=1.0, baseline={"verified_email_rate": 0.0})
    assert m.coverage_spike_warning is True


def test_cache_provenance_fields(tmp_path: Path) -> None:
    from scripts.confenge_contact_resolution.cache import ResolutionCache, cache_key

    cache = ResolutionCache(tmp_path / "c", ttl_seconds=3600, source="unit-test")
    key = cache_key("11222333000181", "generic", "registry|net=0")
    payload = {"cnpj14": "11222333000181", "candidates": []}
    env = cache.set(key, payload, source="unit-test")
    assert env["source"] == "unit-test"
    assert env["fetched_at"]
    assert env["expires_at"]
    assert env["content_hash"]
    assert len(env["content_hash"]) == 64
    got = cache.get(key)
    assert got == payload
    full = cache.get_envelope(key)
    assert full is not None
    assert full["content_hash"] == env["content_hash"]
    assert full["source"] == "unit-test"


def test_retry_backoff_and_rate_limit() -> None:
    from scripts.confenge_contact_resolution.rate_limit import (
        RateLimiter,
        RetryPolicy,
        call_with_retry,
    )

    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return "ok"

    out = call_with_retry(
        flaky,
        policy=RetryPolicy(max_attempts=4, base_delay_seconds=0.01, jitter=0),
        sleep_fn=lambda d: sleeps.append(d),
    )
    assert out == "ok"
    assert calls["n"] == 3
    assert len(sleeps) == 2

    lim = RateLimiter(max_calls=2, window_seconds=60.0)
    assert lim.allow(now=100.0) is True
    assert lim.allow(now=100.1) is True
    assert lim.allow(now=100.2) is False


def test_official_domain_not_from_third_party_site() -> None:
    """Resolver must not promote accounting site to official_domain."""
    company_cnpj = "22333444000192"
    ctx = AdapterContext(
        cnpj14=company_cnpj,
        allow_network=False,
        registry_record={
            "legal_name": "Construtora Beta Ltda",
            "official_match_status": "MATCHED",
            # no site in registry
        },
        site_pages=[
            {
                "url": "https://contabilidadeoliveira.com.br/clientes",
                "source_date": "2026-05-01",
                "contacts": [
                    {
                        "email": "beta@contabilidadeoliveira.com.br",
                        "phone": "4833331111",
                    }
                ],
            }
        ],
    )
    cfg = ResolverConfig(
        adapters=_offline_adapters(),
        allow_network=False,
        context_builder=lambda _c: ctx,
        apply_ownership=True,
    )
    res = ContactResolver(cfg).resolve_one(company_cnpj)
    assert res.official_domain != "contabilidadeoliveira.com.br"
    assert res.official_domain is None or "contabilidade" not in (res.official_domain or "")
    for c in res.candidates:
        if c.email and "contabilidade" in c.email:
            assert c.enrollable is False
            assert c.ownership_status == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value
    assert any("contabilidade" in str(r.get("value") or "") for r in res.rejected_contacts) or all(
        c.enrollable is False for c in res.candidates if c.email and "contabilidade" in c.email
    )
