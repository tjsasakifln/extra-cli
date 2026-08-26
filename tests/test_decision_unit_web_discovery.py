"""Adversarial contract tests for bounded public web discovery."""

from __future__ import annotations

from pathlib import Path

from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    OwnershipStatus,
    PersonObservation,
    PersonRelation,
    SearchAttempt,
    stable_id,
)
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult
from scripts.decision_unit_intelligence.providers.public_search import PublicSearchProvider
from scripts.decision_unit_intelligence.runner import run_account
from scripts.decision_unit_intelligence.web_discovery import (
    CachedRateLimitedSearchBackend,
    CrawlDocument,
    JsonDiscoveryCache,
    SearchBudget,
    SearchHit,
    build_query_plan,
    extract_public_evidence,
    resolve_corporate_domain,
)


class FakeSearch:
    backend_id = "fake"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        self.queries.append(query)
        return [
            SearchHit(
                url="https://empresaexemplo.com.br/institucional/diretoria",
                title="Empresa Exemplo - site oficial",
                snippet="Empresa Exemplo Engenharia. Diretoria e contato institucional.",
                engine="fixture",
            )
        ][:limit]


class FakeCrawler:
    def fetch(self, url: str, *, max_bytes: int) -> CrawlDocument:
        text = (
            "Diretor de Engenharia: João da Silva. "
            "Contato profissional publicado: joao.silva@empresaexemplo.com.br. "
            "Telefone geral (48) 3333-4444. CNPJ 12.345.678/0001-90."
        )
        assert len(text.encode()) < max_bytes
        return CrawlDocument(
            url=url,
            text=text,
            content_type="text/html",
            retrieved_at="2026-08-14T12:00:00Z",
            bytes_touched=len(text.encode()),
        )


class PreloadedProvider:
    provider_id = "preloaded"
    tier = 0

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = context.cnpj
        return ProviderResult(
            legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
            people=[
                PersonObservation(
                    observation_id="qsa-1",
                    company_entity_id=cnpj,
                    person_name="CARLOS SOCIO",
                    observed_role="Sócio-Administrador",
                    relation=PersonRelation.COMPANY_MEMBER,
                    source_type="qsa_rfb",
                    source_url="https://public.example/qsa",
                    epistemic_class=EpistemicClass.OBSERVED,
                    evidence_id="evidence-qsa",
                )
            ],
            channels=[
                ChannelObservation(
                    observation_id="phone-1",
                    company_entity_id=cnpj,
                    channel_type=ChannelType.COMPANY_SWITCHBOARD,
                    channel_value="4833330000",
                    source_type="rfb_cadastre",
                    source_url="https://public.example/cnpj",
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    extra={"person_owns_phone": False},
                )
            ],
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("preloaded", cnpj),
                    company_entity_id=cnpj,
                    tier=0,
                    provider_id=self.provider_id,
                    source="fixture",
                    status="hit",
                )
            ],
        )


def _context() -> InvestigationContext:
    return InvestigationContext(
        cnpj="12345678000190",
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service="reajuste_14133",
    )


def test_query_plan_is_contextual_and_contains_required_public_search_shapes():
    queries = build_query_plan(_context(), known_domain="empresaexemplo.com.br")
    assert '"EMPRESA EXEMPLO ENGENHARIA LTDA" diretor de engenharia' in queries
    assert '"12345678000190" email' in queries
    assert "site:empresaexemplo.com.br contato" in queries
    assert "site:empresaexemplo.com.br filetype:pdf" in queries


def test_domain_resolution_rejects_aggregator_and_preserves_alternatives():
    resolution = resolve_corporate_domain(
        _context(),
        [
            SearchHit("https://cnpj.biz/123", "Empresa Exemplo", "CNPJ 12.345.678/0001-90"),
            SearchHit(
                "https://chapeco.org/associados/empresa-exemplo",
                "Empresa Exemplo",
                "Empresa Exemplo Engenharia, CNPJ 12.345.678/0001-90",
            ),
            SearchHit(
                "https://glassdoor.com.br/empresa/empresa-exemplo",
                "Empresa Exemplo",
                "Empresa Exemplo Engenharia, CNPJ 12.345.678/0001-90",
            ),
            SearchHit(
                "https://empresaexemplo.com.br/quem-somos",
                "Empresa Exemplo - site oficial",
                "Empresa Exemplo Engenharia, CNPJ 12.345.678/0001-90",
            ),
        ],
    )
    assert resolution.canonical_domain == "empresaexemplo.com.br"
    assert resolution.confidence == "HIGH"
    assert all("cnpj.biz" not in candidate.domain for candidate in resolution.alternatives)
    assert all("chapeco.org" not in candidate.domain for candidate in resolution.alternatives)
    assert all("glassdoor.com.br" not in candidate.domain for candidate in resolution.alternatives)


def test_exact_public_page_keeps_identity_role_and_route_dimensions_separate():
    document = FakeCrawler().fetch("https://empresaexemplo.com.br/diretoria", max_bytes=10_000)
    extracted = extract_public_evidence(
        _context(),
        document,
        canonical_domain="empresaexemplo.com.br",
    )
    person = next(person for person in extracted.people if person.person_name == "João da Silva")
    email = next(
        channel for channel in extracted.channels if channel.channel_value == "joao.silva@empresaexemplo.com.br"
    )
    phone = next(channel for channel in extracted.channels if channel.channel_type == ChannelType.COMPANY_SWITCHBOARD)
    assert person.epistemic_class == EpistemicClass.OBSERVED
    assert person.observed_role == "Diretor de Engenharia"
    assert email.epistemic_class == EpistemicClass.OBSERVED
    assert email.person_name == "João da Silva"
    assert email.extra["identity_explicitly_associated"] is True
    assert email.extra["page_cnpj14"] == "12345678000190"
    assert email.extra["page_cnpj_evidence_id"] == email.evidence_id
    assert len(email.extra["page_cnpj_evidence_sha256"]) == 64
    assert any(item.field == "account_mailbox_binding" for item in extracted.evidence)
    assert phone.extra["person_owns_phone"] is False
    assert all(item.source_url == document.url for item in extracted.evidence)


def test_page_without_exact_target_cnpj_does_not_attest_mailbox_identity():
    document = CrawlDocument(
        url="https://empresaexemplo.com.br/contato",
        text="Contato contato@empresaexemplo.com.br. CNPJ 99.888.777/0001-66.",
        content_type="text/html",
        retrieved_at="2026-08-14T12:00:00Z",
        bytes_touched=75,
    )

    extracted = extract_public_evidence(
        _context(),
        document,
        canonical_domain="empresaexemplo.com.br",
    )

    email = next(channel for channel in extracted.channels if channel.channel_value)
    assert "page_cnpj14" not in email.extra
    assert not any(item.field == "account_mailbox_binding" for item in extracted.evidence)


def test_enabled_web_search_runs_before_positive_early_stop_and_persists_evidence():
    search = FakeSearch()
    public_search = PublicSearchProvider(
        backend=search,
        crawler=FakeCrawler(),
        budget=SearchBudget(
            max_queries=2,
            max_results_per_query=2,
            max_pages=1,
            max_bytes=20_000,
            min_query_interval_seconds=0,
        ),
    )
    account = run_account(
        "12345678000190",
        providers=[PreloadedProvider(), public_search],
        infer_email=False,
    )
    attempts = {attempt.provider_id: attempt for attempt in account.ledger.attempts}
    assert search.queries
    assert attempts["public_search"].documents_checked == 1
    assert account.extra["domain_resolution"]["canonical_domain"] == "empresaexemplo.com.br"
    assert any(item.field == "canonical_domain" for item in account.evidence)
    assert any(person.person_name == "João da Silva" for person in account.candidates)
    route = next(
        route
        for route in account.routes
        if route.channel_value == "joao.silva@empresaexemplo.com.br"
    )
    assert route.extra["page_cnpj14"] == "12345678000190"
    assert route.extra["page_cnpj_evidence_id"] in route.evidence_ids


def test_search_backend_off_is_explicit_policy_skip_not_false_coverage():
    provider = PublicSearchProvider()
    result = provider.collect(_context())
    assert result.terminal == "skipped"
    assert result.attempts[0].reason == "search_backend_not_configured"
    assert result.attempts[0].stop_reason == "POLICY_SKIP"


def test_search_cache_reuses_public_discovery_without_a_second_provider_call(tmp_path: Path):
    raw = FakeSearch()
    cached = CachedRateLimitedSearchBackend(
        raw,
        cache=JsonDiscoveryCache(tmp_path, ttl_days=7),
        min_interval_seconds=0,
    )
    first = cached.search('"EMPRESA EXEMPLO" diretor', limit=2)
    second = cached.search('"EMPRESA EXEMPLO" diretor', limit=2)
    assert first == second
    assert len(raw.queries) == 1
    assert cached.cache_misses == 1
    assert cached.cache_hits == 1
