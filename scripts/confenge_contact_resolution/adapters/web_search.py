"""Optional web-search provider interface — disabled by default in tests.

Operational path uses ``build_web_search_provider()`` (DuckDuckGo HTML / Brave).
No private social scraping. No anti-bot evasion. Provider is injectable.
"""

from __future__ import annotations

from typing import Any, Protocol

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.models import RawObservation, SourceProvenance


class WebSearchProvider(Protocol):
    def search_business_contacts(self, cnpj14: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Return public contact snippets with url/date when available."""
        ...


class NoOpWebSearchProvider:
    """Default provider — always empty (safe for CI/tests)."""

    def search_business_contacts(self, cnpj14: str, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class WebSearchAdapter:
    name = "web_search"

    def __init__(self, provider: WebSearchProvider | None = None, *, enabled: bool = False) -> None:
        self.provider = provider or NoOpWebSearchProvider()
        self.enabled = enabled

    def collect(self, ctx: AdapterContext) -> list[RawObservation]:
        if not self.enabled:
            return []
        # Prefer hits already collected by DiscoveryCascade (budgeted)
        prefetched = list(ctx.extra.get("web_search_hits") or [])
        razao = None
        if ctx.registry_record:
            razao = ctx.registry_record.get("legal_name") or ctx.registry_record.get("razao_social")
        results = prefetched
        if not results:
            results = self.provider.search_business_contacts(
                ctx.cnpj14,
                allow_network=ctx.allow_network,
                razao_social=razao,
                nome_fantasia=(ctx.registry_record or {}).get("nome_fantasia"),
            )
        out: list[RawObservation] = []
        for r in results or []:
            email = r.get("email")
            phone = r.get("phone")
            name = r.get("name")
            if not email and not phone and not name:
                continue
            # Explicit ban: private social network sources
            url = str(r.get("url") or "")
            if any(x in url.lower() for x in ("facebook.com", "instagram.com", "tiktok.com")):
                continue
            out.append(
                RawObservation(
                    adapter="web_search",
                    cnpj14=ctx.cnpj14,
                    name=name,
                    cargo=r.get("cargo"),
                    email=email,
                    phone_raw=phone,
                    site=r.get("site") or url,
                    linkedin_public=r.get("linkedin") if "linkedin.com" in str(r.get("linkedin") or "") else None,
                    source=SourceProvenance(
                        source_type="web_search",
                        source_url=r.get("url"),
                        source_date=str(r.get("source_date") or r.get("retrieved_at") or "")[:10] or None,
                        observed_at=str(r.get("retrieved_at") or "") or None,
                        notes="Public web search provider; no private social scrape",
                    ),
                    pattern_guessed_email=bool(r.get("pattern_guessed_email")),
                    epistemic_class="OBSERVED_PUBLIC",
                    context_text=r.get("snippet"),
                )
            )
        return out
