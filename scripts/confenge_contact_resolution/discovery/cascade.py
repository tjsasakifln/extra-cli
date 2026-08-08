"""Discovery cascade: local docs → domain → site crawl → web search (budgeted)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.discovery.budget import (
    DiscoveryBudget,
    DiscoveryStats,
    InvestigationOutcome,
)
from scripts.confenge_contact_resolution.discovery.datalake_docs import lookup_public_docs_for_cnpj
from scripts.confenge_contact_resolution.discovery.domain_probe import probe_official_domain
from scripts.confenge_contact_resolution.discovery.extract import extract_contacts_from_snippet
from scripts.confenge_contact_resolution.discovery.official_domain import (
    DomainResolution,
    resolve_official_domain,
)
from scripts.confenge_contact_resolution.discovery.site_crawl import crawl_official_site, pages_for_site_adapter
from scripts.confenge_contact_resolution.discovery.web_search_providers import (
    build_company_queries,
    build_web_search_provider,
)


@dataclass
class CascadeResult:
    ctx: AdapterContext
    domain: DomainResolution = field(default_factory=DomainResolution)
    stats: DiscoveryStats = field(default_factory=DiscoveryStats)
    search_results: list[dict[str, Any]] = field(default_factory=list)

    def as_meta(self) -> dict[str, Any]:
        return {
            "domain_resolution": self.domain.as_dict(),
            "discovery_stats": self.stats.as_dict(),
            "search_hits": len(self.search_results),
            "site_pages": len(self.ctx.site_pages or []),
            "public_docs": len(self.ctx.public_docs or []),
            "contact_pages": len(self.ctx.contact_pages or []),
        }


class DiscoveryCascade:
    """Fill AdapterContext automatically for production enrich-batch runs."""

    def __init__(
        self,
        *,
        budget: DiscoveryBudget | None = None,
        web_provider: Any | None = None,
        dsn: str | None = None,
        docs_jsonl: list[Path] | None = None,
        allow_network: bool = False,
    ) -> None:
        self.budget = budget or DiscoveryBudget.from_env_or_defaults()
        self.web_provider = web_provider
        self.dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
        self.docs_jsonl = docs_jsonl
        self.allow_network = allow_network
        self._provider = web_provider

    def _provider_instance(self) -> Any:
        if self._provider is not None:
            return self._provider
        self._provider = build_web_search_provider()
        return self._provider

    def run(
        self,
        *,
        cnpj14: str,
        razao_social: str | None = None,
        nome_fantasia: str | None = None,
        registry_record: dict[str, Any] | None = None,
        existing_ctx: AdapterContext | None = None,
        economic_group_id: str | None = None,
        stop_when_strong_contact: bool = True,
    ) -> CascadeResult:
        ctx = existing_ctx or AdapterContext(cnpj14=cnpj14, allow_network=self.allow_network)
        ctx.cnpj14 = cnpj14
        ctx.allow_network = self.allow_network or ctx.allow_network
        if registry_record:
            ctx.registry_record = registry_record
        # Fetch BrasilAPI early so domain probe has fantasia and registry has phones
        if self.allow_network and not ctx.registry_record:
            br = _brasilapi_registry(cnpj14)
            if br:
                ctx.registry_record = br
                registry_record = br
        stats = DiscoveryStats()
        result = CascadeResult(ctx=ctx, stats=stats)

        razao = razao_social or (registry_record or {}).get("legal_name") or (registry_record or {}).get("razao_social")
        fantasia = nome_fantasia or (registry_record or {}).get("nome_fantasia") or (registry_record or {}).get(
            "trade_name"
        )
        registry_site = (registry_record or {}).get("site") or (registry_record or {}).get("website")

        # 1) Local datalake / public docs (cheap)
        if not ctx.public_docs:
            docs = lookup_public_docs_for_cnpj(
                cnpj14,
                dsn=self.dsn,
                jsonl_paths=self.docs_jsonl,
            )
            ctx.public_docs = docs
        if _has_strong_doc_contact(ctx.public_docs) and stop_when_strong_contact:
            # Still try domain from registry for ownership
            result.domain = resolve_official_domain(
                razao_social=razao,
                nome_fantasia=fantasia,
                registry_site=str(registry_site) if registry_site else None,
            )
            if result.domain.is_company_owned_eligible():
                ctx.extra["official_domain"] = result.domain.domain
                ctx.extra["domain_class"] = result.domain.domain_class
            stats.outcome = InvestigationOutcome.CONTACT_FOUND.value
            stats.stop_reason = "strong_public_doc"
            ctx.extra["discovery"] = result.as_meta()
            ctx.extra["economic_group_id"] = economic_group_id
            ctx.extra["investigation_outcome"] = stats.outcome
            return result

        # 2) Cheap name-derived domain probe BEFORE paid/blocked search engines
        if self.allow_network and not stats.budget_exhausted(self.budget):
            try:
                probed = probe_official_domain(
                    razao_social=str(razao) if razao else None,
                    nome_fantasia=str(fantasia) if fantasia else None,
                    max_probes=min(5, max(1, self.budget.max_total_requests // 2)),
                    timeout=3.0,
                )
                stats.total_requests += 2  # DNS+HTTP amortized
                if probed.is_company_owned_eligible():
                    result.domain = probed
            except Exception:  # noqa: BLE001
                stats.errors += 1

        # 3) Lightweight web search fallback (may be blocked in some environments)
        search_hits: list[dict[str, Any]] = []
        need_search = not result.domain.is_company_owned_eligible()
        if self.allow_network and need_search and not stats.budget_exhausted(self.budget):
            provider = self._provider_instance()
            queries = build_company_queries(
                razao_social=razao,
                nome_fantasia=fantasia,
                cnpj14=cnpj14,
                max_queries=min(3, self.budget.max_search_queries),
            )
            empty_streak = 0
            for q in queries:
                if stats.budget_exhausted(self.budget):
                    stats.mark_budget(self.budget)
                    break
                stats.search_queries += 1
                stats.total_requests += 1
                try:
                    if hasattr(provider, "search"):
                        raw = provider.search(q, max_results=6)
                        batch = [r.as_dict() if hasattr(r, "as_dict") else r for r in raw]
                    else:
                        batch = provider.search_business_contacts(
                            cnpj14,
                            allow_network=True,
                            razao_social=razao,
                            nome_fantasia=fantasia,
                            max_queries=1,
                        )
                except Exception:  # noqa: BLE001
                    stats.errors += 1
                    empty_streak += 1
                    if empty_streak >= 2:
                        break  # search provider unusable — stop burning budget
                    continue
                if not batch:
                    empty_streak += 1
                    if empty_streak >= 2:
                        break
                    continue
                empty_streak = 0
                for hit in batch:
                    search_hits.append(hit if isinstance(hit, dict) else {"url": str(hit)})
                if stop_when_strong_contact and _search_has_email(search_hits):
                    break

        result.search_results = search_hits

        # 4) Merge domain signals (probe already may have set result.domain)
        merged = resolve_official_domain(
            razao_social=razao,
            nome_fantasia=fantasia,
            registry_site=str(registry_site) if registry_site else None,
            search_results=search_hits,
        )
        if result.domain.is_company_owned_eligible():
            if merged.is_company_owned_eligible() and merged.confidence > result.domain.confidence:
                result.domain = merged
        else:
            result.domain = merged

        if result.domain.is_company_owned_eligible() and result.domain.domain:
            ctx.extra["official_domain"] = result.domain.domain
            ctx.extra["domain_class"] = result.domain.domain_class
            ctx.extra["domain_resolution"] = result.domain.as_dict()

            # 5) Conservative crawl of official domain
            if self.allow_network and not stats.budget_exhausted(self.budget):
                crawl = crawl_official_site(
                    result.domain.domain,
                    budget=self.budget,
                    stats=stats,
                    allow_network=True,
                )
                site_pages = pages_for_site_adapter(crawl)
                if site_pages:
                    ctx.site_pages = list(ctx.site_pages or []) + site_pages
                    # Contact pages = subset with /contato-like URLs
                    contactish = [
                        p
                        for p in site_pages
                        if any(
                            h in (p.get("url") or "").lower()
                            for h in ("contato", "fale", "contact", "comercial")
                        )
                    ]
                    if contactish:
                        ctx.contact_pages = list(ctx.contact_pages or []) + contactish
                if crawl.contacts and stop_when_strong_contact:
                    stats.outcome = InvestigationOutcome.CONTACT_FOUND.value
                    stats.stop_reason = "official_site_contact"
                    ctx.extra["discovery"] = result.as_meta()
                    ctx.extra["economic_group_id"] = economic_group_id
                    ctx.extra["investigation_outcome"] = stats.outcome
                    return result

        # 6) Inject web-search contacts as contact_pages-like extracts for WebSearchAdapter
        web_contacts: list[dict[str, Any]] = []
        for hit in search_hits:
            contacts = extract_contacts_from_snippet(
                title=hit.get("title"),
                snippet=hit.get("snippet"),
                url=hit.get("url"),
            )
            for c in contacts:
                c["source_type_hint"] = "web_search"
                web_contacts.append(c)
            if hit.get("email") or hit.get("phone"):
                web_contacts.append(hit)
        if web_contacts:
            # Store for provider-less path via contact_pages
            ctx.contact_pages = list(ctx.contact_pages or []) + [
                {"url": c.get("url"), "contacts": [c], "source_date": None} for c in web_contacts if c.get("email") or c.get("phone")
            ]

        # Outcome
        if _ctx_has_any_contact(ctx):
            stats.outcome = InvestigationOutcome.CONTACT_FOUND.value
            stats.stop_reason = stats.stop_reason or "discovery_contacts"
        elif stats.outcome == InvestigationOutcome.BUDGET_EXHAUSTED.value:
            pass
        elif (
            self.allow_network
            and self.budget.max_search_queries > 0
            and stats.search_queries >= self.budget.max_search_queries
        ):
            stats.outcome = InvestigationOutcome.SEARCH_EXHAUSTED.value
            stats.stop_reason = "queries_exhausted"
        else:
            stats.outcome = InvestigationOutcome.NO_CONTACT_YET.value
            stats.stop_reason = stats.stop_reason or "no_public_contact"

        ctx.extra["discovery"] = result.as_meta()
        ctx.extra["economic_group_id"] = economic_group_id
        ctx.extra["investigation_outcome"] = stats.outcome
        # Stash search hits for domain/web adapter enrichment
        ctx.extra["web_search_hits"] = search_hits[:20]
        return result


def _has_strong_doc_contact(docs: list[dict[str, Any]] | None) -> bool:
    for d in docs or []:
        if d.get("email") and d.get("evidence_strength") == "company_authored_document":
            return True
        if d.get("email") and d.get("cnpj14"):
            return True
    return False


def _search_has_email(hits: list[dict[str, Any]]) -> bool:
    for h in hits:
        if h.get("email"):
            return True
        sn = f"{h.get('title') or ''} {h.get('snippet') or ''}"
        if "@" in sn and "." in sn:
            return True
    return False


def _ctx_has_any_contact(ctx: AdapterContext) -> bool:
    for pages in (ctx.site_pages, ctx.contact_pages, ctx.public_docs):
        for p in pages or []:
            if isinstance(p, dict):
                if p.get("email") or p.get("phone"):
                    return True
                for c in p.get("contacts") or []:
                    if c.get("email") or c.get("phone"):
                        return True
    return False


def _brasilapi_registry(cnpj14: str, *, timeout: float = 10.0) -> dict[str, Any] | None:
    """Map BrasilAPI CNPJ payload into registry_record shape."""
    import json
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    c = "".join(ch for ch in (cnpj14 or "") if ch.isdigit())[:14]
    if len(c) != 14:
        return None
    url = f"https://brasilapi.com.br/api/cnpj/v1/{c}"
    req = Request(  # noqa: S310
        url,
        headers={
            "User-Agent": "extra-cli-confenge-contact/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "email": data.get("email"),
        "phone": data.get("ddd_telefone_1") or data.get("telefone"),
        "telefone": data.get("ddd_telefone_1") or data.get("telefone"),
        "legal_name": data.get("razao_social"),
        "razao_social": data.get("razao_social"),
        "nome_fantasia": data.get("nome_fantasia"),
        "trade_name": data.get("nome_fantasia"),
        "company_size": data.get("porte") or data.get("descricao_porte"),
        "source_url": "https://brasilapi.com.br/api/cnpj/v1/",
        "source_date": None,
        "official_match_status": "MATCHED",
        "registration_status": data.get("descricao_situacao_cadastral"),
        "site": data.get("website") or data.get("site"),
    }
