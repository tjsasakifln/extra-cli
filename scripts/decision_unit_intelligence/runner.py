"""Bounded cascade runner used by the CLI."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from scripts.decision_unit_intelligence.email_verification import (
    DnspythonResolver,
    PassiveEmailVerifier,
    verify_email_routes,
)
from scripts.decision_unit_intelligence.models import SearchLedger, normalize_cnpj
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.providers.administrative_process import AdministrativeProcessProvider
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.company_website import CompanyWebsiteProvider
from scripts.decision_unit_intelligence.providers.existing_datalake import ExistingDatalakeProvider
from scripts.decision_unit_intelligence.providers.external_enrichment import ExternalEnrichmentProvider
from scripts.decision_unit_intelligence.providers.historical_campaign import HistoricalCampaignProvider
from scripts.decision_unit_intelligence.providers.official_documents import OfficialDocumentsProvider
from scripts.decision_unit_intelligence.providers.public_search import PublicSearchProvider
from scripts.decision_unit_intelligence.query_planner import ExplicitFallbackBackend, QuerySearchCache
from scripts.decision_unit_intelligence.search_http import SearchBackendUnavailableError, build_search_backend
from scripts.decision_unit_intelligence.site_contact_crawl import SiteCrawlBudget
from scripts.decision_unit_intelligence.web_discovery import (
    CachedPublicCrawler,
    CachedRateLimitedSearchBackend,
    HttpxPublicCrawler,
    JsonDiscoveryCache,
    SearchBudget,
)

_SHARED_HISTORICAL: HistoricalCampaignProvider | None = None


def _build_raw_backend(name: str, *, searxng_url: str | None, timeout_seconds: float):
    if name == "searxng":
        if not searxng_url:
            raise ValueError("searxng search backend requires --searxng-url")
        return SearxngSearchBackend(searxng_url, timeout_seconds=timeout_seconds)
    if name == "ddgs":
        return DdgsSearchBackend(timeout_seconds=timeout_seconds)
    raise ValueError(f"unsupported search backend: {name}")


def default_providers(
    *,
    external_enabled: bool = False,
    search_backend: str = "off",
    searxng_url: str | None = None,
    search_budget: SearchBudget | None = None,
    cache_dir: Path | None = None,
    search_failover: str = "off",
    site_budget: SiteCrawlBudget | None = None,
    site_crawl: bool = True,
    site_crawl_baseline: bool = False,
    query_policy_version: str | None = None,
    search_fallback: str = "off",
) -> list[Any]:
    global _SHARED_HISTORICAL
    if _SHARED_HISTORICAL is None:
        _SHARED_HISTORICAL = HistoricalCampaignProvider()
    budget = search_budget or SearchBudget()
    backend = None
    crawler = None
    planner_cache = None
    policy_version = query_policy_version or "query-policy.v2"
    if search_backend != "off":
        try:
            raw_backend = build_search_backend(
                search_backend,
                searxng_url=searxng_url,
                timeout_seconds=budget.timeout_seconds,
                failover=search_failover,
            )
        except SearchBackendUnavailableError as exc:
            if exc.reason == "missing_url":
                raise ValueError("searxng search backend requires --searxng-url") from exc
            raise
        if search_fallback and search_fallback not in {"off", search_backend}:
            raw_backend = ExplicitFallbackBackend(
                raw_backend,
                build_search_backend(
                    search_fallback,
                    searxng_url=searxng_url,
                    timeout_seconds=budget.timeout_seconds,
                    failover="off",
                ),
            )
        cache = JsonDiscoveryCache(cache_dir or Path(".cache/confenge-prospect"), ttl_days=budget.cache_ttl_days)
        backend = CachedRateLimitedSearchBackend(
            raw_backend,
            cache=cache,
            min_interval_seconds=budget.min_query_interval_seconds,
            policy_version=policy_version,
        )
        planner_cache = QuerySearchCache(cache, policy_version=policy_version)
        crawler = CachedPublicCrawler(
            HttpxPublicCrawler(timeout_seconds=budget.timeout_seconds),
            cache=cache,
        )
    return [
        _SHARED_HISTORICAL,
        ExistingDatalakeProvider(),
        PublicSearchProvider(
            backend=backend,
            crawler=crawler,
            budget=budget,
            policy_version=policy_version,
            planner_cache=planner_cache,
        ),
        AdministrativeProcessProvider(),
        OfficialDocumentsProvider(),
        CompanyWebsiteProvider(
            crawler=crawler if site_crawl else None,
            budget=budget,
            site_budget=site_budget,
            baseline=site_crawl_baseline,
        ),
        ExternalEnrichmentProvider(enabled=external_enabled),
    ]


def run_account(
    cnpj: str,
    *,
    service: str = "reajuste_14133",
    providers: list[Any] | None = None,
    infer_email: bool = True,
    search_backend: str = "off",
    searxng_url: str | None = None,
    search_budget: SearchBudget | None = None,
    cache_dir: Path | None = None,
    verify_email_dns: bool = False,
    search_failover: str = "off",
    site_budget: SiteCrawlBudget | None = None,
    site_crawl: bool = True,
    site_crawl_baseline: bool = False,
    query_policy_version: str | None = None,
    search_fallback: str = "off",
) -> Any:
    started = perf_counter()
    ctx = InvestigationContext(cnpj=normalize_cnpj(cnpj), service=service)
    providers = providers or default_providers(
        search_backend=search_backend,
        searxng_url=searxng_url,
        search_budget=search_budget,
        cache_dir=cache_dir,
        search_failover=search_failover,
        site_budget=site_budget,
        site_crawl=site_crawl,
        site_crawl_baseline=site_crawl_baseline,
        query_policy_version=query_policy_version,
        search_fallback=search_fallback,
    )
    people = []
    channels = []
    evidence = []
    discovery_extra: dict[str, Any] = {}
    ledger = SearchLedger()
    legal_name = None
    why_now = None
    site = None
    blocked = False
    for provider in providers:
        try:
            result = provider.collect(ctx)
        except Exception as exc:
            ledger.blocked_sources.append(f"{provider.provider_id}:{type(exc).__name__}")
            ledger.provider_attempts += 1
            continue
        people.extend(result.people)
        channels.extend(result.channels)
        evidence.extend(result.evidence)
        ledger.attempts.extend(result.attempts)
        ledger.provider_attempts += len(result.attempts)
        ledger.documents_checked += sum(a.documents_checked for a in result.attempts)
        ledger.search_queries.extend([q for a in result.attempts for q in a.queries])
        if any(a.blocked for a in result.attempts):
            ledger.blocked_sources.append(provider.provider_id)
            # A blocked source is not R0 and not exhaustion.
            if provider.tier <= 1 and not people and not channels:
                blocked = True
        if result.legal_name:
            legal_name = result.legal_name
            ctx.legal_name = result.legal_name
        if result.why_now:
            why_now = result.why_now
        if result.company_site:
            site = result.company_site
            ctx.extra["company_site"] = result.company_site
        known = ctx.extra.setdefault("known_people", [])
        for person in result.people:
            name = person.person_name
            if name and name not in known:
                known.append(name)
        if result.extra.get("domain_resolution"):
            discovery_extra["domain_resolution"] = result.extra["domain_resolution"]
            ctx.extra["domain_resolution"] = result.extra["domain_resolution"]
        useful = list(result.extra.get("useful_urls") or [])
        for attempt in result.attempts:
            useful.extend(attempt.extra.get("crawled_urls") or [])
            useful.extend(attempt.extra.get("useful_urls") or [])
        if useful:
            bucket = ctx.extra.setdefault("search_hit_urls", [])
            for url in useful:
                if url not in bucket:
                    bucket.append(url)
        ledger.cost_brl += result.cost.cost_brl
        ledger.bytes_touched += result.cost.bytes_touched + sum(a.bytes_touched for a in result.attempts)
        ledger.tiers_completed.append(provider.tier)
        ledger.known_evidence_checked += len(result.people) + len(result.channels)
        required = {
            p.provider_id for p in providers if getattr(p, "first_class", False) and getattr(p, "enabled", False)
        }
        attempted = {attempt.provider_id for attempt in ledger.attempts}
        # Positive stop only after every enabled first-class provider ran.
        if people and channels and required.issubset(attempted):
            break
    ledger.duration_ms = int((perf_counter() - started) * 1000)
    account = investigate_account(
        cnpj=cnpj,
        legal_name=legal_name,
        service=ctx.service,
        why_now=why_now,
        people=people,
        channels=channels,
        ledger=ledger,
        company_site=site,
        infer_email=infer_email,
        evidence=evidence,
        discovery_extra=discovery_extra,
        blocked=blocked,
    )
    if verify_email_dns:
        verification_cache = JsonDiscoveryCache(cache_dir or Path(".cache/confenge-prospect"), ttl_days=7)
        reports = verify_email_routes(
            account.routes,
            PassiveEmailVerifier(
                DnspythonResolver(),
                cache=verification_cache,
            ),
        )
        account.extra["email_verification"] = [report.to_dict() for report in reports]
    else:
        account.extra["email_verification"] = []
    return account
