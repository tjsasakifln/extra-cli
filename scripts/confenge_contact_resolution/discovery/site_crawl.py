"""Conservative same-domain site crawl for contact extraction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.confenge_contact_resolution.discovery.budget import DiscoveryBudget, DiscoveryStats
from scripts.confenge_contact_resolution.discovery.extract import (
    extract_contacts_from_html,
    extract_internal_links,
    page_title,
    strip_html,
)
from scripts.confenge_contact_resolution.discovery.official_domain import seed_paths_for_domain
from scripts.confenge_contact_resolution.ownership import domain_from_url

_USER_AGENT = "Mozilla/5.0 (compatible; extra-cli-confenge-contact/1.0)"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class FetchedPage:
    url: str
    status: int
    html: str
    title: str | None = None
    error: str | None = None


@dataclass
class SiteCrawlResult:
    domain: str
    pages: list[dict[str, Any]] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def fetch_url(
    url: str,
    *,
    timeout: float = 12.0,
    max_bytes: int = 512_000,
) -> FetchedPage:
    if not url.startswith(("http://", "https://")):
        return FetchedPage(url=url, status=0, html="", error="invalid_scheme")
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"})  # noqa: S310
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = getattr(resp, "status", 200) or 200
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            html = raw.decode("utf-8", errors="replace")
            return FetchedPage(url=url, status=int(status), html=html, title=page_title(html))
    except HTTPError as exc:
        return FetchedPage(url=url, status=int(exc.code), html="", error=f"http_{exc.code}")
    except TimeoutError:
        return FetchedPage(url=url, status=0, html="", error="timeout")
    except (URLError, OSError) as exc:
        return FetchedPage(url=url, status=0, html="", error=type(exc).__name__)


def crawl_official_site(
    domain: str,
    *,
    budget: DiscoveryBudget | None = None,
    stats: DiscoveryStats | None = None,
    timeout: float = 12.0,
    min_interval: float = 0.35,
    allow_network: bool = True,
) -> SiteCrawlResult:
    """Light same-domain crawl: seed paths + homepage internal contactish links."""
    budget = budget or DiscoveryBudget()
    stats = stats or DiscoveryStats()
    domain = (domain or "").lower().removeprefix("www.")
    result = SiteCrawlResult(domain=domain)
    if not domain or not allow_network:
        result.stats = stats.as_dict()
        return result

    seeds = seed_paths_for_domain(domain)[: budget.max_pages_per_domain]
    queue: list[str] = list(seeds)
    seen: set[str] = set()
    last_fetch = 0.0
    all_contacts: list[dict[str, Any]] = []

    while queue and stats.pages_fetched < budget.max_pages and stats.pages_fetched < budget.max_pages_per_domain:
        if stats.budget_exhausted(budget):
            stats.mark_budget(budget)
            break
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        # throttle
        gap = time.monotonic() - last_fetch
        if gap < min_interval:
            time.sleep(min_interval - gap)

        page = fetch_url(url, timeout=timeout, max_bytes=budget.max_bytes_per_page)
        last_fetch = time.monotonic()
        stats.total_requests += 1
        stats.pages_fetched += 1
        if page.error == "timeout":
            stats.timeouts += 1
        if page.status == 429:
            stats.http_429 += 1
            time.sleep(2.0)
        if page.error and not page.html:
            stats.errors += 1
            continue

        contacts = extract_contacts_from_html(page.html, source_url=page.url)
        observed_at = _now()
        for c in contacts:
            # HTTP observation proves that the page was present now; it does
            # not prove when the page or address was published.
            c["source_published_at"] = None
            c["observed_at"] = observed_at
            c["site"] = f"https://{domain}"
        all_contacts.extend(contacts)

        page_row = {
            "url": page.url,
            "title": page.title,
            "contacts": contacts,
            "text_excerpt": strip_html(page.html)[:800] if page.html else "",
            "source_published_at": None,
            "observed_at": observed_at,
        }
        result.pages.append(page_row)

        # Discover more internal links only from homepage / first successful page
        if page.html and stats.pages_fetched <= 2:
            for link in extract_internal_links(page.html, page.url, same_host=domain)[:12]:
                if link not in seen and link not in queue:
                    queue.append(link)

    # Dedupe contacts
    seen_c: set[str] = set()
    for c in all_contacts:
        key = f"{(c.get('email') or '').lower()}|{c.get('phone') or ''}"
        if key in seen_c or key == "|":
            continue
        seen_c.add(key)
        result.contacts.append(c)

    result.stats = stats.as_dict()
    return result


def pages_for_site_adapter(crawl: SiteCrawlResult) -> list[dict[str, Any]]:
    """Shape crawl pages for SiteAdapter injection."""
    out: list[dict[str, Any]] = []
    for p in crawl.pages:
        if p.get("contacts"):
            out.append(p)
    if not out and crawl.contacts:
        out.append(
            {
                "url": f"https://{crawl.domain}/",
                "contacts": crawl.contacts,
                "source_published_at": None,
                "observed_at": next(
                    (str(c.get("observed_at")) for c in crawl.contacts if c.get("observed_at")),
                    None,
                ),
            }
        )
    return out


def domain_of_page_url(url: str | None) -> str | None:
    return domain_from_url(url)
