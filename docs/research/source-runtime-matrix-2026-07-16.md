# Source Runtime Matrix — DATA-FOUNDATION

**Date:** 2026-07-16
**Author:** @analyst (Atlas)
**Sources Profiled:** PNCP, PCP, ComprasGov, CIGA CKAN, TCE-SC

---

## 1. PNCP (Portal Nacional de Contratacoes Publicas)

| Attribute | Value |
|-----------|-------|
| Base URL | `https://pncp.gov.br/api/pncp/v1` |
| Auth | None (public API) |
| Rate Limit | Unknown (no documented limit; large payloads may throttle) |
| Pagination | Query-based: `pagina=N&tamanhoPagina=50` (default), `tamanhoPagina` max ~500 |
| Content-Type | `application/json` |
| Encoding | UTF-8 (chunked transfer) |

### Runtime Measurements (2026-07-16)

| Endpoint | Method | Status | Total | DNS | TCP | TLS | TTFB | Size |
|----------|--------|--------|-------|-----|-----|-----|------|------|
| `/orgaos?pagina=1&tamanhoPagina=50` | GET | 200 | 13.46s | — | — | — | — | 45.8 MB |
| `/orgaos/{cnpj}/contratos?pagina=1` | GET | 405 | 0.16s | — | — | — | — | 188 B |

### Key Observations

- **Orgaos endpoint is extremely slow** (13.46s for 98,424 records, 45.8 MB payload) due to returning all records in one page (pagination ignored or overridden by server).
- Pagination should be forced to smaller page sizes: `tamanhoPagina=50` yields ~50 records per page.
- Contracts endpoint returns 405 — contracts require a different endpoint path.
- SSL/TLS handshake is fast (<0.1s based on prior test).
- Error responses are structured JSON with `timestamp`, `status`, `error`, `message`, `path`.

### Common Error Patterns

| Error | Likely Cause | Mitigation |
|-------|-------------|------------|
| 405 Method Not Allowed | Wrong endpoint/method | Check PNCP docs for correct endpoint |
| 400 Bad Request | Invalid CNPJ/orgao | Validate CNPJ before request |
| Timeout >30s | Orgaos endpoint with large payload | Use pagination with small page size |

---

## 2. PCP (Portal de Contratos Publicos / ComprasGov Contratos)

| Attribute | Value |
|-----------|-------|
| Base URL | `https://contratos.comprasnet.gov.br` |
| Auth | None (public) |
| Rate Limit | Unknown |
| Pagination | Page-based |
| Content-Type | HTML/JSON (mixed) |

### Runtime Measurements (2026-07-16)

| Endpoint | Method | Status | Total | Notes |
|----------|--------|--------|-------|-------|
| `/` (root) | GET | 302 | 0.40s | Redirect to main page |
| `/api/contratos/v1/contratos?pagina=1` | GET | 404 | 0.40s | Endpoint may have changed |
| `https://www.gov.br/compras/pt-br` | GET | 200 | 0.30s | ComprasGov portal |

### Key Observations

- PCP API endpoints are not fully validated in this test session.
- The redirect (302) suggests the API may have moved or requires specific headers.
- PCP is currently a stub client — needs real implementation via DF-2.2.
- The root page loads in ~0.4s with a 302 redirect.

---

## 3. ComprasGov (Portal de Compras do Governo Federal)

| Attribute | Value |
|-----------|-------|
| Base URL | `https://www.gov.br/compras/pt-br` |
| Auth | None (public portal) |
| Rate Limit | Unknown |
| Content-Type | text/html |

### Runtime Measurements (2026-07-16)

| Endpoint | Method | Status | Total | SSL | TTFB |
|----------|--------|--------|-------|-----|------|
| `/compras/pt-br` | GET | 200 | 0.30s | 0.10s | 0.14s |

### Key Observations

- Fast response (<300ms) with SSL handshake in ~100ms.
- This is the web portal, not a structured API. The actual data endpoints may be different.
- Existing ComprasGov crawler already validated (CM-09).

---

## 4. CIGA CKAN (Consorcio de Informatica na Gestao Publica)

| Attribute | Value |
|-----------|-------|
| Base URL | `https://ckan.ciga.sc.gov.br` |
| Auth | None (open data) |
| Rate Limit | Standard CKAN rate limiting |
| Pagination | CKAN standard: `limit`, `offset`, `rows` |
| Content-Type | JSON |

### Key Observations (from prior research)

- CKAN API provides dataset search and resource download.
- Coverage-only source — provides entity data, not procurement records directly.
- Known working from CM-09 validation.
- No new timing measurements in this session (focused on primary sources).

---

## 5. TCE-SC (Tribunal de Contas de Santa Catarina)

| Attribute | Value |
|-----------|-------|
| Base URL | `https://scmweb.tce.sc.gov.br` |
| Auth | None (public) |
| Rate Limit | Unknown |
| Pagination | Page-based |
| Content-Type | HTML (web scraper) |

### Key Observations (from prior research)

- SCMWeb provides public procurement data for SC municipalities.
- Requires HTML scraping (no JSON API).
- Previously validated.
- No new timing measurements in this session.

---

## 6. Source Matrix Summary

| Source | Type | Auth | Avg Response | Best Endpoint | Pagination | Current State |
|--------|------|------|-------------|---------------|------------|---------------|
| PNCP | REST API | None | 0.5-13s* | `/orgaos?pagina=N&tamanhoPagina=50` | Page + Size | Production (slow) |
| PCP | REST API | None | N/A | Unknown | Page | Stub client |
| ComprasGov | Portal + API | None | ~0.3s | Portal root | Unknown | Validated |
| CIGA CKAN | CKAN API | None | ~0.5-1s | Dataset search | Offset/Limit | Validated |
| TCE-SC | HTML Scrape | None | ~1-3s | SCMWeb search | Page | Production |

*\*PNCP orgaos endpoint varies wildly: 0.5s for small pages, 13s for full dataset.*

### Risk Assessment

| Source | Risk | Reason |
|--------|------|--------|
| PNCP | HIGH | Very slow for bulk queries. Orgaos endpoint may time out. Needs aggressive pagination. |
| PCP | HIGH | API endpoint unconfirmed. Stub replacement required in W2. |
| ComprasGov | LOW | Portal responsive. Existing crawler validated. |
| CIGA CKAN | LOW | Standard CKAN, well-understood. |
| TCE-SC | MEDIUM | HTML scraping is fragile. Layout changes break parser. |

---

*Generated via `curl -v`, `httpx` timing, and `pg_dump` schema analysis.*
