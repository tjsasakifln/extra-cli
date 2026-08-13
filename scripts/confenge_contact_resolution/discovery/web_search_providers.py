"""Pluggable public web-search providers for contact discovery.

Default operational provider: DuckDuckGo HTML (no API key).
Optional: Brave Search API when BRAVE_SEARCH_API_KEY is set.
Never scrapes private social networks or bypasses CAPTCHA.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scripts.confenge_contact_resolution.discovery.extract import extract_contacts_from_snippet

_USER_AGENT = "Mozilla/5.0 (compatible; extra-cli-confenge-contact/1.0; +https://github.com/tjsasakifln/extra-cli)"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SearchResult:
    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = "web_search"
    retrieved_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
        }


def build_company_queries(
    *,
    razao_social: str | None,
    nome_fantasia: str | None = None,
    cnpj14: str | None = None,
    max_queries: int = 6,
) -> list[str]:
    """Adaptive query set — strongest first; caller stops early on hits."""
    razao = (razao_social or "").strip()
    fantasia = (nome_fantasia or "").strip()
    cnpj = re.sub(r"\D", "", cnpj14 or "")[:14]
    # Shorten long razão for better search recall
    razao_short = razao
    for noise in (
        " LTDA",
        " EIRELI",
        " S.A.",
        " S/A",
        " SA",
        " ME",
        " EPP",
        " CONSTRUCOES",
        " CONSTRUÇÕES",
        " ENGENHARIA",
    ):
        pass
    if len(razao_short) > 60:
        razao_short = " ".join(razao.split()[:6])

    queries: list[str] = []
    if razao:
        queries.append(f'"{razao_short}" contato')
        queries.append(f'"{razao_short}" email')
        queries.append(f'"{razao_short}" "fale conosco"')
    if fantasia and fantasia.lower() not in (razao or "").lower():
        queries.append(f'"{fantasia}" contato')
    if cnpj and len(cnpj) == 14:
        queries.append(f"{cnpj} email")
        queries.append(f"{cnpj} telefone")
    if razao:
        queries.append(f'"{razao_short}" licitações')
        queries.append(f'"{razao_short}" comercial')
        queries.append(f'"{razao_short}" engenharia site')
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[: max(1, max_queries)]


def build_source_ladder_queries(
    *,
    razao_social: str | None,
    cnpj14: str | None,
) -> list[tuple[str, str]]:
    """One explicit query per institutional source-ladder stage.

    Search results are discovery leads only. They still need an auditable page
    or document before a recipient can pass the human-evidence gate.
    """
    razao = " ".join((razao_social or "").strip().split()[:8])
    cnpj = re.sub(r"\D", "", cnpj14 or "")[:14]
    key = f'"{razao}"' if razao else cnpj
    return [
        ("process_administrative_docs", f'{key} "representante legal" email proposta contrato'),
        ("pncp_transparency_compras", f"{key} site:gov.br email contrato OR proposta"),
        (
            "professional_councils_associations",
            f'{key} (CREA OR CAU OR associação) email "responsável técnico"',
        ),
        ("company_public_pages", f"{key} (diretor OR gerente OR responsável) email"),
    ]


class DuckDuckGoHTMLProvider:
    """Public HTML search — no API key. Rate-limit politely.

    Note: some networks block html.duckduckgo.com; callers should fail fast and
    fall back to domain probe + registry.
    """

    name = "duckduckgo_html"

    def __init__(self, *, timeout: float = 6.0, min_interval: float = 0.5) -> None:
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_call = 0.0
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._consecutive_failures = 0
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        """Whether this process can still query the provider honestly."""
        return self._consecutive_failures < 3

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.monotonic()

    def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        q = (query or "").strip()
        if not q:
            return []
        if q in self._cache:
            return [
                SearchResult(**{**r, "retrieved_at": r.get("retrieved_at") or _now()})
                for r in self._cache[q][:max_results]
            ]

        if self._consecutive_failures >= 3:
            self.last_error = "provider_circuit_open"
            return []  # provider unusable this process lifetime
        self._throttle()
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
        req = Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
        try:
            with urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                html = resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._consecutive_failures += 1
            self.last_error = type(exc).__name__
            return []

        results = parse_duckduckgo_html(html, source=self.name)
        if not results:
            self._consecutive_failures += 1
            self.last_error = "unparseable_or_empty_response"
        else:
            self._consecutive_failures = 0
            self.last_error = None
        self._cache[q] = [r.as_dict() for r in results]
        return results[:max_results]

    def search_business_contacts(self, cnpj14: str, **kwargs: Any) -> list[dict[str, Any]]:
        """WebSearchProvider protocol — extract contact-ish fields from snippets."""
        allow = kwargs.get("allow_network", True)
        if not allow:
            return []
        razao = kwargs.get("razao_social") or kwargs.get("company_name")
        fantasia = kwargs.get("nome_fantasia")
        max_q = int(kwargs.get("max_queries") or 4)
        queries = build_company_queries(
            razao_social=str(razao) if razao else None,
            nome_fantasia=str(fantasia) if fantasia else None,
            cnpj14=cnpj14,
            max_queries=max_q,
        )
        out: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for q in queries:
            for r in self.search(q, max_results=6):
                # Always emit search hit for domain discovery even without email
                contacts = extract_contacts_from_snippet(title=r.title, snippet=r.snippet, url=r.url)
                if contacts:
                    for c in contacts:
                        key = f"{c.get('email') or ''}|{c.get('phone') or ''}|{r.url}"
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        out.append(
                            {
                                **c,
                                "url": r.url,
                                "title": r.title,
                                "snippet": r.snippet,
                                "source": r.source,
                                "retrieved_at": r.retrieved_at,
                                "query": q,
                            }
                        )
                else:
                    # Domain signal only
                    key = f"url:{r.url}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        out.append(
                            {
                                "url": r.url,
                                "title": r.title,
                                "snippet": r.snippet,
                                "source": r.source,
                                "retrieved_at": r.retrieved_at,
                                "query": q,
                                "site": r.url,
                            }
                        )
            if len(out) >= 12:
                break
        return out


_RESULT_BLOCK_RE = re.compile(
    r'(?is)<div[^>]+class="[^"]*result[^"]*"[^>]*>.*?</div>\s*(?=<div[^>]+class="[^"]*result|</div>\s*</div>\s*</div>|$)',
)
_A_RE = re.compile(r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>')
_SNIP_RE = re.compile(
    r'(?is)<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
    r'<td[^>]+class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>'
)
_HREF_UDDG = re.compile(r"[?&]uddg=([^&]+)")


def _clean_html_text(s: str) -> str:
    t = re.sub(r"<[^>]+>", " ", s or "")
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _unwrap_ddg_url(href: str) -> str:
    href = href or ""
    m = _HREF_UDDG.search(href)
    if m:
        return unquote(m.group(1))
    # Sometimes //duckduckgo.com/l/?uddg=...
    if "uddg=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        except (TypeError, ValueError, KeyError):
            return href
    return href


def parse_duckduckgo_html(html: str, *, source: str = "duckduckgo_html") -> list[SearchResult]:
    """Parse DDG HTML result page into SearchResult list (testable offline)."""
    results: list[SearchResult] = []
    # Prefer result__a anchors
    for m in _A_RE.finditer(html or ""):
        href = _unwrap_ddg_url(m.group(1))
        title = _clean_html_text(m.group(2))
        if not href or not href.startswith("http"):
            continue
        if "duckduckgo.com" in href:
            continue
        # Snippet: look ahead a bit
        start = m.end()
        window = html[start : start + 800]
        snip_m = re.search(
            r'(?is)class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|td|div)>',
            window,
        )
        snippet = _clean_html_text(snip_m.group(1)) if snip_m else ""
        results.append(SearchResult(title=title, url=href, snippet=snippet, source=source, retrieved_at=_now()))
    if results:
        return results

    # Fallback: generic organic links
    for m in re.finditer(r'(?is)<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', html or ""):
        href = _unwrap_ddg_url(m.group(1))
        title = _clean_html_text(m.group(2))
        if "duckduckgo.com" in href or not title or len(title) < 3:
            continue
        results.append(SearchResult(title=title, url=href, snippet="", source=source, retrieved_at=_now()))
        if len(results) >= 10:
            break
    return results


class BraveSearchProvider:
    """Brave Search API — requires BRAVE_SEARCH_API_KEY."""

    name = "brave_search"

    def __init__(self, api_key: str, *, timeout: float = 12.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return self.last_error is None

    def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        q = (query or "").strip()
        if not q:
            return []
        if q in self._cache:
            return [SearchResult(**r) for r in self._cache[q][:max_results]]
        url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(q)}&count={max_results}"
        req = Request(  # noqa: S310
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            self.last_error = type(exc).__name__
            return []
        results: list[SearchResult] = []
        for item in (data.get("web") or {}).get("results") or []:
            results.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("description") or ""),
                    source=self.name,
                    retrieved_at=_now(),
                )
            )
        self._cache[q] = [r.as_dict() for r in results]
        self.last_error = None
        return results[:max_results]

    def search_business_contacts(self, cnpj14: str, **kwargs: Any) -> list[dict[str, Any]]:
        # Delegate shape to DuckDuckGo-compatible extractor path
        ddg_like = DuckDuckGoHTMLProvider()
        # Monkey: reuse query builder + extract via local search
        allow = kwargs.get("allow_network", True)
        if not allow:
            return []
        razao = kwargs.get("razao_social") or kwargs.get("company_name")
        queries = build_company_queries(
            razao_social=str(razao) if razao else None,
            nome_fantasia=kwargs.get("nome_fantasia"),
            cnpj14=cnpj14,
            max_queries=int(kwargs.get("max_queries") or 4),
        )
        out: list[dict[str, Any]] = []
        for q in queries:
            for r in self.search(q):
                contacts = extract_contacts_from_snippet(title=r.title, snippet=r.snippet, url=r.url)
                if contacts:
                    for c in contacts:
                        out.append({**c, "url": r.url, "title": r.title, "snippet": r.snippet, "source": r.source})
                else:
                    out.append(
                        {
                            "url": r.url,
                            "title": r.title,
                            "snippet": r.snippet,
                            "source": r.source,
                            "site": r.url,
                        }
                    )
        _ = ddg_like  # keep import path stable for type checkers
        return out


def _unwrap_bing_url(href: str) -> str:
    """Decode Bing's `u=a1<base64url>` redirect without following trackers."""
    value = (parse_qs(urlparse(unescape(href or "")).query).get("u") or [""])[0]
    if value.startswith("a1"):
        encoded = value[2:]
        try:
            return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return href
    return href


def parse_bing_html(html: str) -> list[SearchResult]:
    """Parse Bing organic result blocks; tracking URLs are decoded locally."""
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[SearchResult] = []
    for item in soup.select("li.b_algo"):
        anchor = item.select_one("h2 a[href]")
        if anchor is None:
            continue
        href = _unwrap_bing_url(str(anchor.get("href") or ""))
        if not href.startswith(("http://", "https://")) or "bing.com/ck/" in href:
            continue
        snippet_node = item.select_one(".b_caption p") or item.select_one("p")
        out.append(
            SearchResult(
                title=anchor.get_text(" ", strip=True),
                url=href,
                snippet=snippet_node.get_text(" ", strip=True) if snippet_node else "",
                source="bing_html",
                retrieved_at=_now(),
            )
        )
    return out


class BingHTMLProvider:
    """Public Bing HTML fallback with explicit circuit-breaker state."""

    name = "bing_html"

    def __init__(self, *, timeout: float = 8.0, min_interval: float = 0.5) -> None:
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_call = 0.0
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._consecutive_failures = 0
        self.last_error: str | None = None

    @property
    def available(self) -> bool:
        return self._consecutive_failures < 3

    def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        q = (query or "").strip()
        if not q:
            return []
        if q in self._cache:
            return [SearchResult(**row) for row in self._cache[q][:max_results]]
        if not self.available:
            self.last_error = "provider_circuit_open"
            return []
        gap = time.monotonic() - self._last_call
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last_call = time.monotonic()
        url = f"https://www.bing.com/search?q={quote_plus(q)}&count={max_results}"
        req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html"})  # noqa: S310
        try:
            with urlopen(req, timeout=self.timeout) as response:  # noqa: S310
                html = response.read(1_500_000).decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._consecutive_failures += 1
            self.last_error = type(exc).__name__
            return []
        results = parse_bing_html(html)
        if results:
            self._consecutive_failures = 0
            self.last_error = None
        else:
            self._consecutive_failures += 1
            self.last_error = "unparseable_or_empty_response"
        self._cache[q] = [row.as_dict() for row in results]
        return results[:max_results]

    def search_business_contacts(self, cnpj14: str, **kwargs: Any) -> list[dict[str, Any]]:
        if not kwargs.get("allow_network", True):
            return []
        out: list[dict[str, Any]] = []
        for query in build_company_queries(
            razao_social=kwargs.get("razao_social") or kwargs.get("company_name"),
            nome_fantasia=kwargs.get("nome_fantasia"),
            cnpj14=cnpj14,
            max_queries=int(kwargs.get("max_queries") or 4),
        ):
            for result in self.search(query, max_results=6):
                contacts = extract_contacts_from_snippet(
                    title=result.title,
                    snippet=result.snippet,
                    url=result.url,
                )
                out.extend({**contact, **result.as_dict(), "site": result.url} for contact in (contacts or [{}]))
        return out


class CompositeWebSearchProvider:
    """Try providers in order; first that returns results wins per query."""

    def __init__(self, providers: list[Any]) -> None:
        self.providers = providers

    @property
    def available(self) -> bool:
        return any(bool(getattr(p, "available", True)) for p in self.providers)

    @property
    def last_error(self) -> str | None:
        errors = [str(getattr(p, "last_error")) for p in self.providers if getattr(p, "last_error", None)]
        return ",".join(errors) or None

    def search(self, query: str, *, max_results: int = 8) -> list[SearchResult]:
        for p in self.providers:
            if hasattr(p, "search"):
                res = p.search(query, max_results=max_results)
                if res:
                    return res
        return []

    def search_business_contacts(self, cnpj14: str, **kwargs: Any) -> list[dict[str, Any]]:
        for p in self.providers:
            res = p.search_business_contacts(cnpj14, **kwargs)
            if res:
                return res
        return []


def build_web_search_provider(*, prefer: str | None = None) -> Any:
    """Factory: env-driven pluggable provider (never NoOp when network path is chosen)."""
    prefer = (prefer or os.environ.get("CONFENGE_WEB_SEARCH_PROVIDER") or "auto").lower()
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY")
    providers: list[Any] = []
    if prefer in {"brave", "auto"} and brave_key:
        providers.append(BraveSearchProvider(brave_key))
    if prefer in {"duckduckgo", "ddg", "auto", "brave"}:
        providers.append(DuckDuckGoHTMLProvider())
    if prefer in {"bing", "auto", "brave"}:
        providers.append(BingHTMLProvider())
    if not providers:
        providers.append(DuckDuckGoHTMLProvider())
    if len(providers) == 1:
        return providers[0]
    return CompositeWebSearchProvider(providers)
