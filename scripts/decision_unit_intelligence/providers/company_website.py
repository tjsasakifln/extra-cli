"""Tier 3: specialized corporate-site contact crawl after a defensible domain exists."""

from __future__ import annotations

from time import perf_counter
from urllib.parse import urlsplit

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult
from scripts.decision_unit_intelligence.site_contact_crawl import (
    SITE_CRAWL_VERSION,
    SiteCrawlBudget,
    run_site_contact_crawl,
)
from scripts.decision_unit_intelligence.web_discovery import SearchBudget, WebCrawler


class CompanyWebsiteProvider:
    provider_id = "company_website"
    tier = 3

    def __init__(
        self,
        *,
        crawler: WebCrawler | None = None,
        budget: SearchBudget | None = None,
        site_budget: SiteCrawlBudget | None = None,
        baseline: bool = False,
    ) -> None:
        self.crawler = crawler
        self.budget = budget
        self.site_budget = site_budget or SiteCrawlBudget()
        self.baseline = baseline
        self.enabled = crawler is not None
        self.first_class = bool(self.enabled)

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        domain = _canonical_domain(context)
        attempt = SearchAttempt(
            attempt_id=stable_id("att", self.provider_id, cnpj, domain or "", SITE_CRAWL_VERSION),
            company_entity_id=cnpj,
            tier=self.tier,
            provider_id=self.provider_id,
            source="company_site",
            status="skipped",
            extra={
                "site_crawl_version": SITE_CRAWL_VERSION,
                "budget": self.site_budget.to_dict(),
                "baseline": self.baseline,
            },
        )
        if self.crawler is None:
            attempt.reason = "site_crawler_not_configured"
            attempt.stop_reason = "POLICY_SKIP"
            return ProviderResult(attempts=[attempt], terminal="skipped")
        if not domain:
            attempt.reason = "no_defensible_domain"
            attempt.stop_reason = "POLICY_SKIP"
            return ProviderResult(attempts=[attempt], terminal="skipped")

        started = perf_counter()
        crawl = run_site_contact_crawl(
            crawler=self.crawler,
            context=context,
            canonical_domain=domain,
            seed_urls=list(context.extra.get("search_hit_urls") or []),
            budget=self.site_budget,
            baseline=self.baseline,
            rate_limit=False,
        )
        attempt.documents_checked = len(crawl.visited)
        attempt.bytes_touched = int(crawl.budget.get("bytes_touched") or 0)
        attempt.duration_ms = int((perf_counter() - started) * 1000)
        attempt.extra["site_crawl"] = crawl.to_dict()
        attempt.extra["high_value_urls"] = crawl.high_value_urls
        attempt.extra["metrics"] = crawl.metrics
        named = any((channel.extra or {}).get("identity_explicitly_associated") for channel in crawl.channels)
        if named or crawl.channels or crawl.people:
            attempt.status = "hit"
            attempt.reason = None
        else:
            attempt.status = "miss"
            attempt.reason = "no_site_contact_evidence"
        attempt.stop_reason = crawl.stop_reason
        return ProviderResult(
            people=crawl.people,
            channels=crawl.channels,
            evidence=crawl.evidence,
            attempts=[attempt],
            terminal=attempt.status,
            company_site=f"https://{domain}",
            extra={
                "domain_resolution": context.extra.get("domain_resolution")
                or {"canonical_domain": domain, "confidence": "CONTEXT"},
                "site_crawl": crawl.to_dict(),
            },
        )


def _canonical_domain(context: InvestigationContext) -> str | None:
    resolution = context.extra.get("domain_resolution") or {}
    domain = resolution.get("canonical_domain") if isinstance(resolution, dict) else None
    if domain:
        return str(domain).lower().removeprefix("www.")
    site = str(context.extra.get("company_site") or "")
    if not site:
        return None
    candidate = site if "://" in site else f"https://{site}"
    host = (urlsplit(candidate).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None
