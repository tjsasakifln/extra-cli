"""Discovery cascade: local docs → domain → site crawl → web search (budgeted)."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
from scripts.confenge_contact_resolution.discovery.public_document_fetch import (
    fetch_cnpj_linked_public_document,
)
from scripts.confenge_contact_resolution.discovery.site_crawl import crawl_official_site, pages_for_site_adapter
from scripts.confenge_contact_resolution.discovery.web_search_providers import (
    build_company_queries,
    build_source_ladder_queries,
    build_web_search_provider,
)


@dataclass
class CascadeResult:
    ctx: AdapterContext
    domain: DomainResolution = field(default_factory=DomainResolution)
    stats: DiscoveryStats = field(default_factory=DiscoveryStats)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    source_attempts: list[dict[str, Any]] = field(default_factory=list)

    def as_meta(self) -> dict[str, Any]:
        return {
            "domain_resolution": self.domain.as_dict(),
            "discovery_stats": {
                **self.stats.as_dict(),
                "source_attempts": list(self.source_attempts),
                "sources_attempted": list(dict.fromkeys(str(a.get("source_adapter")) for a in self.source_attempts)),
            },
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

    @staticmethod
    def _attempt(
        result: CascadeResult,
        *,
        cnpj14: str,
        source_adapter: str,
        source_url: str | None,
        outcome: str,
        reason_code: str,
        limitations: list[str] | None = None,
        source_published_at: str | None = None,
    ) -> None:
        stable = "|".join([cnpj14, source_adapter, source_url or "", outcome, reason_code, source_published_at or ""])
        terminal_state = (
            "CONTACT_EVIDENCE_FOUND"
            if outcome == "FOUND"
            else "SOURCE_EXTERNAL_BLOCKER"
            if outcome == "EXTERNAL_BLOCKER"
            else "SOURCE_EXHAUSTED"
        )
        next_action = (
            None
            if outcome == "FOUND"
            else "external_source_access_required"
            if outcome == "EXTERNAL_BLOCKER"
            else "continue_source_ladder"
        )
        result.source_attempts.append(
            {
                "cnpj14": cnpj14,
                "source_adapter": source_adapter,
                "source_url": source_url,
                "source_published_at": source_published_at,
                "observed_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "outcome": outcome,
                "reason_code": reason_code,
                "limitations": list(limitations or []),
                "evidence_sha256": hashlib.sha256(stable.encode("utf-8")).hexdigest(),
                "terminal_state": terminal_state,
                "next_action": next_action,
            }
        )

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
        fantasia = (
            nome_fantasia or (registry_record or {}).get("nome_fantasia") or (registry_record or {}).get("trade_name")
        )
        registry_site = (registry_record or {}).get("site") or (registry_record or {}).get("website")

        # Preload already-ingested documents, but evaluate the literal ladder
        # in official-site-first order below.
        if not ctx.public_docs:
            docs = lookup_public_docs_for_cnpj(
                cnpj14,
                dsn=self.dsn,
                jsonl_paths=self.docs_jsonl,
            )
            ctx.public_docs = docs

        # 1) Official company site: resolve and crawl before accepting other sources.
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

        # Official-site discovery fallback (may be blocked in some environments).
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

        # Merge official-domain signals (probe already may have set result.domain).
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

            # Conservative crawl of official domain.
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
                        if any(h in (p.get("url") or "").lower() for h in ("contato", "fale", "contact", "comercial"))
                    ]
                    if contactish:
                        ctx.contact_pages = list(ctx.contact_pages or []) + contactish
                named_site = _contacts_have_named_human(crawl.contacts)
                self._attempt(
                    result,
                    cnpj14=cnpj14,
                    source_adapter="official_site",
                    source_url=f"https://{result.domain.domain}/",
                    outcome="FOUND" if named_site else "NO_VALID_HUMAN_RECIPIENT",
                    reason_code="named_human_contact_found" if named_site else "site_has_no_explicit_named_email_role",
                    limitations=[] if named_site else ["generic_or_unassociated_contacts_do_not_count"],
                )
                if named_site and stop_when_strong_contact:
                    stats.outcome = InvestigationOutcome.CONTACT_FOUND.value
                    stats.stop_reason = "official_site_named_human_contact"
                    ctx.extra["discovery"] = result.as_meta()
                    ctx.extra["economic_group_id"] = economic_group_id
                    ctx.extra["investigation_outcome"] = stats.outcome
                    return result
        else:
            self._attempt(
                result,
                cnpj14=cnpj14,
                source_adapter="official_site",
                source_url=None,
                outcome="NOT_FOUND",
                reason_code="official_domain_not_proven",
                limitations=["no_unambiguous_company_domain"],
            )

        # 2) Company-authored administrative/public-process documents already
        # tied to this CNPJ by the datalake.
        named_doc = _has_strong_doc_contact(ctx.public_docs, cnpj14=cnpj14)
        self._attempt(
            result,
            cnpj14=cnpj14,
            source_adapter="process_administrative_docs",
            source_url=next(
                (
                    str(d.get("url") or d.get("source_url"))
                    for d in (ctx.public_docs or [])
                    if d.get("url") or d.get("source_url")
                ),
                None,
            ),
            outcome="FOUND" if named_doc else "NO_VALID_HUMAN_RECIPIENT",
            reason_code="named_human_contact_found" if named_doc else "documents_have_no_explicit_named_email_role",
        )
        if named_doc and stop_when_strong_contact:
            stats.outcome = InvestigationOutcome.CONTACT_FOUND.value
            stats.stop_reason = "strong_named_public_doc"
            ctx.extra["discovery"] = result.as_meta()
            ctx.extra["economic_group_id"] = economic_group_id
            ctx.extra["investigation_outcome"] = stats.outcome
            return result

        # 3–5) PNCP/transparency, councils/associations and complementary
        # corporate pages. Search snippets are never final evidence.
        if self.allow_network:
            provider = self._provider_instance()
            for adapter_name, query in build_source_ladder_queries(
                razao_social=str(razao) if razao else None,
                cnpj14=cnpj14,
            ):
                if adapter_name == "process_administrative_docs":
                    continue
                if stats.budget_exhausted(self.budget):
                    stats.mark_budget(self.budget)
                    self._attempt(
                        result,
                        cnpj14=cnpj14,
                        source_adapter=adapter_name,
                        source_url=None,
                        outcome="EXTERNAL_BLOCKER",
                        reason_code="discovery_budget_exhausted",
                        limitations=[stats.stop_reason],
                    )
                    continue
                stats.search_queries += 1
                stats.total_requests += 1
                search_failed = False
                try:
                    raw = provider.search(query, max_results=3) if hasattr(provider, "search") else []
                    batch = [r.as_dict() if hasattr(r, "as_dict") else r for r in raw]
                except Exception as exc:  # noqa: BLE001
                    batch = []
                    search_failed = True
                    stats.errors += 1
                    limitation = type(exc).__name__
                else:
                    provider_error = getattr(provider, "last_error", None)
                    provider_available = bool(getattr(provider, "available", True))
                    limitation = (
                        f"search_provider_unavailable:{provider_error or 'unknown'}"
                        if not provider_available
                        else "search_returned_no_auditable_result"
                        if not batch
                        else "search_hits_require_source_document_validation"
                    )
                relevant_batch = [
                    hit
                    for hit in batch
                    if isinstance(hit, dict)
                    and _relevant_ladder_hit(
                        adapter_name,
                        hit,
                        cnpj14=cnpj14,
                        razao_social=str(razao) if razao else None,
                    )
                ]
                rejected_hits = len(batch) - len(relevant_batch)
                search_hits.extend(relevant_batch)
                validated_docs: list[dict[str, Any]] = []
                fetch_errors: list[str] = []
                hit_urls = [str(hit.get("url") or "") for hit in relevant_batch if hit.get("url")]
                remaining_requests = max(0, self.budget.max_total_requests - stats.total_requests)
                remaining_pages = max(0, self.budget.max_pages - stats.pages_fetched)
                allowed = hit_urls[: min(remaining_requests, remaining_pages)]
                if len(allowed) < len(hit_urls):
                    fetch_errors.append("budget:document_fetch_capacity")
                fetch_timeout = min(12.0, max(3.0, self.budget.max_seconds / 4))
                fetch_bytes = min(2_000_000, max(self.budget.max_bytes_per_page, 512_000))
                with ThreadPoolExecutor(max_workers=max(1, min(3, len(allowed)))) as pool:
                    fetched_results = list(
                        pool.map(
                            lambda hit_url: fetch_cnpj_linked_public_document(
                                hit_url,
                                cnpj14=cnpj14,
                                timeout=fetch_timeout,
                                max_bytes=fetch_bytes,
                                official_company_domain=result.domain.domain,
                            ),
                            allowed,
                        )
                    )
                for fetched in fetched_results:
                    stats.total_requests += 1
                    stats.pages_fetched += 1
                    if fetched.error and fetched.error != "exact_cnpj_not_present":
                        fetch_errors.append(fetched.error)
                    validated_docs.extend(fetched.as_public_docs())
                if validated_docs:
                    ctx.public_docs = list(ctx.public_docs or []) + validated_docs
                named_validated = _has_strong_doc_contact(validated_docs, cnpj14=cnpj14)
                provider_blocked = not bool(getattr(provider, "available", True))
                unresolved_external = (
                    search_failed or provider_blocked or bool(relevant_batch and fetch_errors and not validated_docs)
                )
                outcome = (
                    "FOUND"
                    if named_validated
                    else "EXTERNAL_BLOCKER"
                    if unresolved_external
                    else "NO_VALID_HUMAN_RECIPIENT"
                    if relevant_batch
                    else "NOT_FOUND"
                )
                self._attempt(
                    result,
                    cnpj14=cnpj14,
                    source_adapter=adapter_name,
                    source_url=next((str(h.get("url")) for h in batch if isinstance(h, dict) and h.get("url")), None),
                    outcome=outcome,
                    reason_code=(
                        "named_human_contact_found"
                        if named_validated
                        else "source_document_fetch_failed"
                        if relevant_batch and unresolved_external
                        else "search_provider_unavailable"
                        if unresolved_external
                        else "searched_documents_have_no_explicit_cnpj_linked_person_email_role"
                        if relevant_batch
                        else "no_final_person_email_evidence"
                    ),
                    limitations=[limitation, f"irrelevant_search_hits:{rejected_hits}", *fetch_errors],
                    source_published_at=next(
                        (str(d.get("source_published_at")) for d in validated_docs if d.get("source_published_at")),
                        None,
                    ),
                )
                if named_validated and stop_when_strong_contact:
                    stats.outcome = InvestigationOutcome.CONTACT_FOUND.value
                    stats.stop_reason = f"{adapter_name}_named_human_contact"
                    ctx.extra["discovery"] = result.as_meta()
                    ctx.extra["economic_group_id"] = economic_group_id
                    ctx.extra["investigation_outcome"] = stats.outcome
                    return result

        # 6) Registry/QSA is corroboration only and never a source for inferred email.
        self._attempt(
            result,
            cnpj14=cnpj14,
            source_adapter="official_registry_corroboration",
            source_url=str((registry_record or {}).get("source_url") or "official_company_registry"),
            outcome="CORROBORATED" if registry_record else "NOT_FOUND",
            reason_code="registry_never_infers_email",
            limitations=["QSA_or_company_status_only"],
        )

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
                {"url": c.get("url"), "contacts": [c], "source_date": None}
                for c in web_contacts
                if c.get("email") or c.get("phone")
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


def _has_strong_doc_contact(docs: list[dict[str, Any]] | None, *, cnpj14: str) -> bool:
    target = re.sub(r"\D", "", cnpj14 or "")[:14]
    for d in docs or []:
        document_cnpj = re.sub(
            r"\D",
            "",
            str(d.get("cnpj14") or d.get("cnpj") or d.get("supplier_cnpj") or ""),
        )[:14]
        if (
            len(target) == 14
            and document_cnpj == target
            and d.get("email")
            and not d.get("pattern_guessed_email")
            and (d.get("name") or d.get("nome") or d.get("representante"))
            and (d.get("cargo") or d.get("funcao"))
            and (d.get("url") or d.get("source_url") or d.get("document_id") or d.get("document"))
            and d.get("evidence_strength") in {"company_authored_document", "official_cnpj_linked_document"}
        ):
            return True
    return False


_COMPANY_TOKEN_NOISE = frozenset(
    {
        "ltda",
        "eireli",
        "empresa",
        "engenharia",
        "construtora",
        "construcoes",
        "servicos",
        "comercio",
        "industria",
        "brasil",
    }
)


def _fold(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower())


def _relevant_ladder_hit(
    adapter_name: str,
    hit: dict[str, Any],
    *,
    cnpj14: str,
    razao_social: str | None,
) -> bool:
    """Reject obvious search-engine noise before downloading a result."""
    url = str(hit.get("url") or "")
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    blob = _fold(f"{url} {hit.get('title') or ''} {hit.get('snippet') or ''}")
    cnpj = re.sub(r"\D", "", cnpj14 or "")[:14]
    if cnpj and cnpj in re.sub(r"\D", "", blob):
        return True
    tokens = [token for token in _fold(razao_social).split() if len(token) >= 5 and token not in _COMPANY_TOKEN_NOISE]
    token_matches = sum(1 for token in set(tokens) if token in blob)
    if adapter_name == "pncp_transparency_compras":
        return host.endswith((".gov.br", ".leg.br", ".jus.br")) or host in {
            "pncp.gov.br",
            "portaldecompraspublicas.com.br",
        }
    if adapter_name == "professional_councils_associations":
        institutional = any(marker in host or marker in blob for marker in ("crea", "cau", "associ", "sind", "abenc"))
        return institutional and token_matches >= 1
    if adapter_name == "company_public_pages":
        host_folded = _fold(host).replace(" ", "")
        required_matches = min(2, max(1, len(set(tokens))))
        return any(token in host_folded for token in tokens) or token_matches >= required_matches
    return False


def _contacts_have_named_human(contacts: list[dict[str, Any]] | None) -> bool:
    return any(
        c.get("email")
        and c.get("name")
        and (c.get("cargo") or c.get("role") or c.get("funcao"))
        and not c.get("pattern_guessed_email")
        for c in (contacts or [])
    )


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
