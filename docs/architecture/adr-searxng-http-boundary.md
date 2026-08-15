# ADR: Private SearXNG over an HTTP boundary

**Status:** Accepted for the CONFENGE contact-discovery search backend  
**Date:** 2026-08-14  
**Supersedes / extends:** [`adr-decision-unit-intelligence.md`](adr-decision-unit-intelligence.md) (HTTP-only SearXNG clause)

## Decision

Contact discovery in extra-cli uses a **CONFENGE-controlled SearXNG instance** as the batch web-search backend. extra-cli is only an HTTP client:

```
extra-cli --search-backend searxng
        --searxng-url / CONFENGE_SEARXNG_URL
        → GET {url}/search?q=…&format=json
        → private SearXNG (official image, pinned digest)
        → conservative public engines
```

SearXNG/AGPL source is not copied, vendored, imported, or linked into extra-cli.

## Consequences

- Missing URL, HTTP 429, HTTP 5xx, timeout, invalid JSON, and an open circuit fail closed as backend unavailability (`SOURCE_BLOCKED` via `SearchBackendUnavailableError`). They are never an empty successful hit list.
- Public third-party instances (searx.space and listed public hosts) are rejected unless `CONFENGE_SEARXNG_ALLOW_PUBLIC=1`.
- DDGS remains the MIT local canary / explicit operator re-run. In-process failover is `--search-failover ddgs` or `CONFENGE_SEARCH_FAILOVER=ddgs` and is recorded on the backend id. Default is off.
- Operators who modify the official image or ship a derived SearXNG must offer corresponding source (AGPL-3.0 §13 network use). Config-only use of the official image still documents that obligation.
- No purchased data, authenticated scraping, CAPTCHA bypass, or proxy rotation.

Operational kit: [`../ops/searxng-private-backend.md`](../ops/searxng-private-backend.md).
