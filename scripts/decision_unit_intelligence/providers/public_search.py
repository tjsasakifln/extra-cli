"""First-class, bounded public search and official-site evidence discovery."""

from __future__ import annotations

from time import perf_counter

from scripts.confenge_contact_resolution.mailbox_purpose import is_mailbox_controlled_eligible
from scripts.decision_unit_intelligence.email_discovery import discover_internal_targets
from scripts.decision_unit_intelligence.evidence import make_evidence
from scripts.decision_unit_intelligence.models import EpistemicClass, SearchAttempt, normalize_cnpj, now_iso, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult
from scripts.decision_unit_intelligence.query_planner import (
    ExplicitFallbackBackend,
    aggregate_executions,
    default_policy,
    execute_plan,
    load_policy,
    plan_queries,
)
from scripts.decision_unit_intelligence.web_discovery import (
    SearchBackend,
    SearchBudget,
    WebCrawler,
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
        policy_version: str | None = None,
        planner_cache=None,
    ) -> None:
        self.backend = backend
        self.crawler = crawler
        self.budget = budget or SearchBudget()
        self.enabled = backend is not None
        self.policy = load_policy(policy_version) if policy_version else default_policy()
        self.planner_cache = planner_cache

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        known_site = str(context.extra.get("company_site") or "") or None
        known_people = [str(name) for name in (context.extra.get("known_people") or []) if name]
        known_domain = _domain(known_site)
        plan = plan_queries(
            context,
            policy=self.policy,
            known_domain=known_domain,
            known_people=known_people,
            max_queries=self.budget.max_queries,
        )
        queries = [spec.query for spec in plan.specs]
        attempt = SearchAttempt(
            attempt_id=stable_id("att", self.provider_id, cnpj, "|".join(queries)),
            company_entity_id=cnpj,
            tier=self.tier,
            provider_id=self.provider_id,
            source="public_web",
            status="skipped",
            queries=queries,
            extra={
                "planned_query_count": len(plan.specs),
                "query_policy_version": self.policy.version,
                "adaptive_mode": plan.adaptive_mode,
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
        run = execute_plan(
            plan,
            self.backend,
            policy=self.policy,
            cache=self.planner_cache,
            limit=self.budget.max_results_per_query,
            legal_name=context.legal_name,
            known_people=known_people,
        )
        executed = [row for row in run.executions if row.executed]
        attempt.queries = [row.spec.query for row in executed]
        hits = dedupe_search_hits(run.hits)
        failures = [f"{row.failure}:{row.spec.query}" for row in run.executions if row.failure]
        resolution = resolve_corporate_domain(context, hits, known_site=known_site)
        attempt.extra["search_backend"] = self.backend.backend_id
        attempt.extra["result_count"] = len(hits)
        attempt.extra["failures"] = failures
        attempt.extra["domain_resolution"] = resolution.to_dict()
        attempt.extra["query_executions"] = [row.to_dict() for row in run.executions]
        attempt.extra["query_yield"] = aggregate_executions(run.executions)
        if isinstance(self.backend, ExplicitFallbackBackend) and self.backend.events:
            attempt.extra["fallback_events"] = [event.to_dict() for event in self.backend.events]
        useful_urls = [
            hit.url for hit in hits if resolution.canonical_domain and _domain(hit.url) == resolution.canonical_domain
        ]
        attempt.extra["useful_urls"] = useful_urls

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
        identity_yield = False
        if self.crawler and resolution.canonical_domain:
            seed_limit = max(2, min(self.budget.max_pages, (self.budget.max_pages + 1) // 2))
            queued = rank_crawl_urls(hits, resolution.canonical_domain, limit=seed_limit)
            remaining_bytes = self.budget.max_bytes
            seen = set(queued)
            index = 0
            while index < len(queued) and remaining_bytes > 0:
                url = queued[index]
                index += 1
                try:
                    document = self.crawler.fetch(url, max_bytes=remaining_bytes)
                except Exception as exc:
                    crawl_failures.append(f"{type(exc).__name__}:{url}")
                    continue
                crawled_urls.append(document.url)
                bytes_touched += document.bytes_touched
                remaining_bytes -= document.bytes_touched
                extracted = extract_public_evidence(
                    context,
                    document,
                    canonical_domain=resolution.canonical_domain,
                )
                people.extend(extracted.people)
                channels.extend(extracted.channels)
                evidence.extend(extracted.evidence)
                if any((channel.extra or {}).get("identity_explicitly_associated") for channel in extracted.channels):
                    identity_yield = True
                control_eligible_yield = any(
                    channel.channel_value
                    and is_mailbox_controlled_eligible(str(channel.channel_value))
                    and str((channel.extra or {}).get("page_cnpj14") or "") == cnpj
                    and (channel.extra or {}).get("company_associated") is True
                    for channel in extracted.channels
                )
                # A named mailbox is not account identity. Continue the bounded
                # crawl until an exact CNPJ-bound controlled route is observed.
                if control_eligible_yield:
                    break
                for link in discover_internal_targets(
                    links=document.links,
                    html=document.html,
                    canonical_domain=resolution.canonical_domain,
                    already=seen,
                    limit=self.budget.max_pages,
                    page_url=document.url,
                ):
                    if len(queued) >= self.budget.max_pages:
                        break
                    queued.append(link)
                    seen.add(link)

        attempt.documents_checked = len(crawled_urls)
        attempt.bytes_touched = bytes_touched
        attempt.duration_ms = int((perf_counter() - started) * 1000)
        attempt.extra["crawled_urls"] = crawled_urls
        attempt.extra["crawl_failures"] = crawl_failures
        attempt.extra["identity_yield"] = identity_yield
        attempt.extra["known_people_queried"] = known_people
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
            extra={
                "domain_resolution": resolution.to_dict(),
                "useful_urls": list(attempt.extra.get("useful_urls") or []),
            },
        )


def _domain(site: str | None) -> str | None:
    if not site:
        return None
    from urllib.parse import urlsplit

    candidate = site if "://" in site else f"https://{site}"
    host = (urlsplit(candidate).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None
