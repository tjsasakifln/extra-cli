"""First-class, bounded public search and official-site evidence discovery."""

from __future__ import annotations

from time import perf_counter

from scripts.decision_unit_intelligence.evidence import make_evidence
from scripts.decision_unit_intelligence.models import EpistemicClass, SearchAttempt, normalize_cnpj, now_iso, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult
from scripts.decision_unit_intelligence.web_discovery import (
    SearchBackend,
    SearchBudget,
    WebCrawler,
    build_query_plan,
    dedupe_search_hits,
    extract_public_evidence,
    rank_crawl_urls,
    resolve_corporate_domain,
)


class PublicSearchProvider:
    provider_id = "public_search"
    tier = 1
    first_class = True

    def __init__(
        self,
        *,
        backend: SearchBackend | None = None,
        crawler: WebCrawler | None = None,
        budget: SearchBudget | None = None,
    ) -> None:
        self.backend = backend
        self.crawler = crawler
        self.budget = budget or SearchBudget()
        self.enabled = backend is not None

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        known_site = str(context.extra.get("company_site") or "") or None
        plan = build_query_plan(context, known_domain=_domain(known_site))
        queries = plan[: self.budget.max_queries]
        attempt = SearchAttempt(
            attempt_id=stable_id("att", self.provider_id, cnpj, "|".join(queries)),
            company_entity_id=cnpj,
            tier=self.tier,
            provider_id=self.provider_id,
            source="public_web",
            status="skipped",
            queries=queries,
            extra={
                "planned_query_count": len(plan),
                "budget": {
                    "max_queries": self.budget.max_queries,
                    "max_results_per_query": self.budget.max_results_per_query,
                    "max_pages": self.budget.max_pages,
                    "max_bytes": self.budget.max_bytes,
                },
            },
        )
        if self.backend is None:
            attempt.reason = "search_backend_not_configured"
            attempt.stop_reason = "POLICY_SKIP"
            return ProviderResult(attempts=[attempt], terminal="skipped")
        if not context.legal_name:
            attempt.reason = "legal_name_required_for_targeted_search"
            attempt.stop_reason = "POLICY_SKIP"
            return ProviderResult(attempts=[attempt], terminal="skipped")

        started = perf_counter()
        search_cache_before = (
            int(getattr(self.backend, "cache_hits", 0)),
            int(getattr(self.backend, "cache_misses", 0)),
        )
        crawl_cache_before = (
            int(getattr(self.crawler, "cache_hits", 0)),
            int(getattr(self.crawler, "cache_misses", 0)),
        )
        hits = []
        failures: list[str] = []
        for query in queries:
            try:
                hits.extend(self.backend.search(query, limit=self.budget.max_results_per_query))
            except Exception as exc:  # provider failures are preserved, not promoted to evidence
                failures.append(f"{type(exc).__name__}:{query}")
        hits = dedupe_search_hits(hits)
        resolution = resolve_corporate_domain(context, hits, known_site=known_site)
        attempt.extra["search_backend"] = self.backend.backend_id
        attempt.extra["result_count"] = len(hits)
        attempt.extra["failures"] = failures
        attempt.extra["domain_resolution"] = resolution.to_dict()

        evidence = []
        if resolution.canonical_domain:
            domain_evidence = make_evidence(
                field="canonical_domain",
                value=resolution.canonical_domain,
                epistemic_class=EpistemicClass.CORROBORATED,
                source_type="public_search",
                source_url=resolution.alternatives[0].evidence_urls[0],
                evidence_snippet="; ".join(resolution.reason_codes),
                observed_at=now_iso(),
                extraction_method="explainable_domain_resolution",
                extra={"confidence": resolution.confidence},
            )
            evidence.append(domain_evidence)

        people = []
        channels = []
        crawled_urls: list[str] = []
        bytes_touched = 0
        crawl_failures: list[str] = []
        if self.crawler and resolution.canonical_domain:
            urls = rank_crawl_urls(hits, resolution.canonical_domain, limit=self.budget.max_pages)
            remaining_bytes = self.budget.max_bytes
            for url in urls:
                if remaining_bytes <= 0:
                    break
                try:
                    document = self.crawler.fetch(url, max_bytes=remaining_bytes)
                except Exception as exc:
                    crawl_failures.append(f"{type(exc).__name__}:{url}")
                    continue
                crawled_urls.append(document.url)
                bytes_touched += document.bytes_touched
                remaining_bytes -= document.bytes_touched
                extracted = extract_public_evidence(context, document)
                people.extend(extracted.people)
                channels.extend(extracted.channels)
                evidence.extend(extracted.evidence)

        attempt.documents_checked = len(crawled_urls)
        attempt.bytes_touched = bytes_touched
        attempt.duration_ms = int((perf_counter() - started) * 1000)
        attempt.extra["crawled_urls"] = crawled_urls
        attempt.extra["crawl_failures"] = crawl_failures
        attempt.extra["cache_hits"] = (
            int(getattr(self.backend, "cache_hits", 0))
            - search_cache_before[0]
            + int(getattr(self.crawler, "cache_hits", 0))
            - crawl_cache_before[0]
        )
        attempt.extra["cache_misses"] = (
            int(getattr(self.backend, "cache_misses", 0))
            - search_cache_before[1]
            + int(getattr(self.crawler, "cache_misses", 0))
            - crawl_cache_before[1]
        )
        attempt.status = "hit" if resolution.canonical_domain or people or channels else "miss"
        attempt.reason = None if attempt.status == "hit" else "no_defensible_web_evidence"
        if failures and not hits:
            attempt.status = "blocked"
            attempt.blocked = True
            attempt.reason = "all_search_queries_failed"
            attempt.stop_reason = "SOURCE_BLOCKED"
        elif len(queries) >= self.budget.max_queries and not (people or channels):
            attempt.stop_reason = "BUDGET_EXHAUSTED"
        return ProviderResult(
            people=people,
            channels=channels,
            evidence=evidence,
            attempts=[attempt],
            terminal=attempt.status,
            company_site=(f"https://{resolution.canonical_domain}" if resolution.canonical_domain else known_site),
            extra={"domain_resolution": resolution.to_dict()},
        )


def _domain(site: str | None) -> str | None:
    if not site:
        return None
    from urllib.parse import urlsplit

    candidate = site if "://" in site else f"https://{site}"
    host = (urlsplit(candidate).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None
