"""Identifier-based web discovery for process portals (Bing HTML, no API key).

Snippets never promote EMAIL_SEND_READY — only primary URLs are returned.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse

import requests

USER_AGENT = "extra-cli-confenge-web-discovery/1.0"


def bing_search(query: str, *, max_results: int = 8, session: requests.Session | None = None) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)
    sess.headers.setdefault("Accept", "text/html")
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={max_results}"
    try:
        resp = sess.get(url, timeout=(5, 12))
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    html = resp.text
    results: list[dict[str, Any]] = []
    # Prefer cite domains + nearby anchors
    for href in re.findall(r'<a[^>]+href="(https?://[^"]+)"', html, flags=re.I):
        if any(x in href for x in ("bing.com", "microsoft.", "w3.org", "javascript:")):
            continue
        if not href.startswith("http"):
            continue
        host = urlparse(href).netloc.lower()
        if not host:
            continue
        title = host
        results.append({"url": href, "title": title, "snippet": "", "source": "bing_html"})
        if len(results) >= max_results:
            break
    # de-dupe by url
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)
    return out


def discover_process_urls(
    *,
    process_number: str | None,
    company_name: str | None = None,
    company_cnpj: str | None = None,
    session: requests.Session | None = None,
    max_queries: int = 4,
) -> list[dict[str, Any]]:
    from scripts.confenge_process_enrichment.process_resolve import build_discovery_queries

    queries = build_discovery_queries(
        process_number=process_number,
        company_name=company_name,
        company_cnpj=company_cnpj,
        contract_number=None,
    )[:max_queries]
    # Prefer SEI/process-oriented queries first
    boosted = []
    for q in queries:
        boosted.append(q)
        if process_number:
            boosted.append(f'{q} SEI OR "consulta processo" OR protocolo')
    seen_q: set[str] = set()
    ordered = []
    for q in boosted:
        if q not in seen_q:
            seen_q.add(q)
            ordered.append(q)

    hits: list[dict[str, Any]] = []
    seen_u: set[str] = set()
    for q in ordered[:max_queries]:
        for h in bing_search(q, session=session, max_results=6):
            u = h.get("url") or ""
            if u in seen_u:
                continue
            # Prefer gov / sei / transparency
            ul = u.lower()
            if not any(x in ul for x in (".gov.br", "sei.", "transparencia", "protocolo", "processo")):
                continue
            seen_u.add(u)
            h = dict(h)
            h["query"] = q
            hits.append(h)
    return hits
