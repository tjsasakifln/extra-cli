"""Metrics partition, pattern-guess single count, domain class, economic group."""

from __future__ import annotations

from pathlib import Path

from scripts.confenge_contact_resolution.adapters.contact_pages import ContactPageAdapter
from scripts.confenge_contact_resolution.adapters.public_docs import PublicDocsAdapter
from scripts.confenge_contact_resolution.adapters.registry import RegistryAdapter
from scripts.confenge_contact_resolution.adapters.site import SiteAdapter
from scripts.confenge_contact_resolution.adapters.web_search import NoOpWebSearchProvider, WebSearchAdapter
from scripts.confenge_contact_resolution.discovery.official_domain import (
    DomainClass,
    classify_host,
    resolve_official_domain,
)
from scripts.confenge_contact_resolution.discovery.web_search_providers import (
    build_company_queries,
    parse_duckduckgo_html,
)
from scripts.confenge_contact_resolution.email_policy import assess_email
from scripts.confenge_contact_resolution.enrichment_batch import (
    CompanyJob,
    EnrichmentBatchRunner,
    EnrichmentMetrics,
    accumulate_metrics,
)
from scripts.confenge_contact_resolution.models import (
    AccountContactResolution,
    ContactCandidate,
    EmailVerificationLayers,
    OwnershipStatus,
    SourceProvenance,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.ownership import (
    primary_rejection_reason,
    rejected_contact_dict,
)
from scripts.confenge_contact_resolution.resolver import ResolverConfig
from scripts.confenge_contact_resolution.reuse_graph import ContactReuseGraph


def _cand_pattern() -> ContactCandidate:
    ea = assess_email("joao.silva@empresa.com.br", pattern_guessed=True)
    return ContactCandidate(
        candidate_id="pg1",
        cnpj14="11222333000181",
        account_key="11222333000181",
        email=ea.email,
        email_display=ea.email_display,
        source=SourceProvenance(source_type="web_search", source_url="https://empresa.com.br"),
        verification_status=VerificationStatus.CANDIDATE_UNVERIFIED.value,
        email_layers=ea.layers or EmailVerificationLayers(pattern_guessed=True),
        confidence=0.2,
        enrollable=False,
        ownership_status=OwnershipStatus.UNRESOLVED.value,
        ownership_reason="pattern_guessed_email_never_enrollable",
        verification_reason="PATTERN_GUESS",
    )


def test_pattern_guess_primary_rejection_once():
    c = _cand_pattern()
    # layers.pattern_guessed + CANDIDATE_UNVERIFIED together → one PATTERN_GUESS
    assert c.email_layers and c.email_layers.pattern_guessed
    assert c.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value
    assert primary_rejection_reason(c) == "PATTERN_GUESS"
    d = rejected_contact_dict(c)
    assert d["primary_rejection_reason"] == "PATTERN_GUESS"


def test_accumulate_metrics_pattern_guess_not_double_counted():
    metrics = EnrichmentMetrics()
    c = _cand_pattern()
    res = AccountContactResolution(
        cnpj14="11222333000181",
        account_key="11222333000181",
        candidates=[c],
        rejected_contacts=[],
    )
    accumulate_metrics(metrics, res)
    metrics.finalize(duration_s=1.0)
    assert metrics.pattern_guesses_rejected == 1
    assert metrics.rejected_total == 1
    assert metrics.rejected_by_primary_reason["PATTERN_GUESS"] == 1
    # Must not inflate by counting CANDIDATE_UNVERIFIED again
    assert metrics.rejected_by_primary_reason["PATTERN_GUESS"] == metrics.pattern_guesses_rejected


def test_accumulate_metrics_rejected_partition_no_double_count():
    metrics = EnrichmentMetrics()
    res = AccountContactResolution(
        cnpj14="11222333000181",
        account_key="11222333000181",
        candidates=[],
        rejected_contacts=[
            {
                "value": "contato@contabilxyz.com.br",
                "ownership_status": OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value,
                "third_party_type": "ACCOUNTING",
                "reason": "accounting_office",
                "primary_rejection_reason": "ACCOUNTING",
            },
            {
                "value": "shared@escritorio.com",
                "ownership_status": OwnershipStatus.SHARED_EXTERNAL_CONTACT.value,
                "primary_rejection_reason": "SHARED_EXTERNAL",
            },
        ],
    )
    accumulate_metrics(metrics, res)
    metrics.finalize(duration_s=1.0)
    assert metrics.rejected_total == 2
    assert metrics.accounting_contacts_rejected == 1
    assert metrics.shared_external_contacts_rejected == 1
    # partition sums to total
    assert sum(metrics.rejected_by_primary_reason.values()) == metrics.rejected_total


def test_domain_classification_blocks_directories_and_social():
    assert classify_host("jusbrasil.com.br").domain_class == DomainClass.DIRECTORY.value
    assert classify_host("linkedin.com").domain_class in {
        DomainClass.DIRECTORY.value,
        DomainClass.THIRD_PARTY.value,
    }
    assert classify_host("facebook.com").domain_class in {
        DomainClass.DIRECTORY.value,
        DomainClass.THIRD_PARTY.value,
    }
    assert classify_host("pncp.gov.br").domain_class == DomainClass.DIRECTORY.value


def test_domain_resolution_prefers_company_aligned_host():
    res = resolve_official_domain(
        razao_social="PAVSANTOS CONSTRUTORA LTDA",
        search_results=[
            {"url": "https://www.jusbrasil.com.br/tudo", "title": "PAVSANTOS", "snippet": "cnpj"},
            {"url": "https://www.pavsantos.com.br/contato", "title": "Pavsantos", "snippet": "engenharia"},
        ],
    )
    assert res.domain == "pavsantos.com.br"
    assert res.is_company_owned_eligible()


def test_duckduckgo_html_parser_offline():
    html = """
    <div class="result results_links">
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fempresa.com.br%2Fcontato">
        Empresa Contato
      </a>
      <a class="result__snippet">Email comercial@empresa.com.br telefone</a>
    </div>
    """
    results = parse_duckduckgo_html(html)
    assert results
    assert "empresa.com.br" in results[0].url


def test_build_company_queries_adaptive():
    qs = build_company_queries(
        razao_social="FOO BAR CONSTRUCOES LTDA",
        cnpj14="11222333000181",
        max_queries=4,
    )
    assert len(qs) <= 4
    assert any("contato" in q for q in qs)


def test_budget_zero_search_does_not_exhaust_immediately():
    """max_search_queries=0 means disabled, not already exhausted."""
    from scripts.confenge_contact_resolution.discovery.budget import DiscoveryBudget, DiscoveryStats

    b = DiscoveryBudget(max_search_queries=0, max_pages=4, max_total_requests=10, max_seconds=30)
    s = DiscoveryStats()
    assert not s.budget_exhausted(b)
    s.pages_fetched = 4
    assert s.budget_exhausted(b)


def test_economic_group_propagation_in_reuse_graph(tmp_path: Path):
    """Case 2: different CNPJ roots, same economic_group_id → same_group share allowed."""
    g = ContactReuseGraph()
    c1 = "11222333000181"
    c2 = "99888777000166"  # different root
    g.register_company(c1, economic_group_id="GRP-ALPHA")
    g.register_company(c2, economic_group_id="GRP-ALPHA")
    g.observe_email("comercial@holding.com.br", c1)
    g.observe_email("comercial@holding.com.br", c2)
    sig = g.signal_for_email("comercial@holding.com.br", c1)
    assert sig is not None
    assert sig.same_group_count >= 1
    assert sig.unrelated_count == 0


def test_unrelated_reuse_is_negative(tmp_path: Path):
    g = ContactReuseGraph()
    phones = []
    for i in range(10):
        c = f"{i:08d}0001{i:02d}"[:14].ljust(14, "0")
        # ensure 14 digits
        c = (f"{10000000 + i}0001{i:02d}")[:14]
        g.register_company(c)
        g.observe_phone("11999990000", c)
        phones.append(c)
    sig = g.signal_for_phone("11999990000", phones[0])
    assert sig is not None
    assert sig.unrelated_count >= 5


def test_enrich_batch_human_review_pending(tmp_path: Path):
    """Human review package is PENDING never PASS; fixtures offline path."""
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    cnpj = "11222333000181"
    (fixtures / f"{cnpj}_site.json").write_text(
        """[{"url":"https://acme-engenharia.com.br/contato","contacts":[
          {"email":"licitacoes@acme-engenharia.com.br","name":"Comercial"}
        ]}]""",
        encoding="utf-8",
    )
    adapters = [
        RegistryAdapter(prefer_network=False),
        SiteAdapter(),
        PublicDocsAdapter(),
        ContactPageAdapter(),
        WebSearchAdapter(provider=NoOpWebSearchProvider(), enabled=False),
    ]
    cfg = ResolverConfig(
        adapters=adapters,
        fixtures_dir=fixtures,
        allow_network=False,
        apply_ownership=True,
    )
    out = tmp_path / "run"
    runner = EnrichmentBatchRunner(output_dir=out, resolver_config=cfg, run_id="test-hr")
    summary = runner.run(
        [CompanyJob(cnpj14=cnpj, razao_social="ACME ENGENHARIA LTDA")],
        resume=False,
    )
    assert summary["ok"]
    hr = out / "human-review"
    assert (hr / "review.md").is_file()
    assert (hr / "status.json").is_file()
    import json

    status = json.loads((hr / "status.json").read_text(encoding="utf-8"))
    assert status["human_validation"] == "HUMAN_REVIEW_PENDING"
    assert status["human_validation"] != "HUMAN_REVIEW_PASS"
