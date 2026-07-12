# DOM-SC Crawler Diagnostic Report

> **Date:** 2026-07-11
> **Lookback:** 90 days (2026-04-12 to 2026-07-11)
> **Context:** Story COVERAGE-1.5 — DOM-SC Crawler Expansion

## Executive Summary

The DOM-SC API endpoint `?r=remote/search` has been **removed** and replaced by `?r=remote/list`. The old endpoint returns HTTP 404 for all category queries. The new endpoint uses a different response schema and natively supports pagination via `page` + `count` parameters. The crawler requires an update to call the new endpoint and handle the new response format.

**Root cause of coverage gap:** The old crawler calls a now-defunct API endpoint. Once migrated to the new endpoint, the crawler should recover full functionality.

---

## 1. Credentials Status

| Variable | Status |
|----------|--------|
| `DOM_SC_CPF` | MISSING (not set in dev environment) |
| `DOM_SC_CNPJ` | MISSING (not set in dev environment) |
| `DOM_SC_API_KEY` | MISSING (not set in dev environment) |

**Verdict:** Credentials are not available in this dev environment (expected for security). The API requires valid credentials — returns 401 with dummy values. Production env vars must be set before crawl.

## 2. Site Accessibility

| Endpoint | URL | Status | Details |
|----------|-----|--------|---------|
| homepage | `https://diariomunicipal.sc.gov.br/` | OK | 200, 96334 bytes, HTML |
| api_docs | `?r=site/page&view=integracao` | OK | 200, 69236 bytes, full API docs |
| site_login | `?r=site/login` | OK | 200, 18456 bytes |

**Verdict:** Site is online and fully accessible. API documentation page is functional.

## 3. API Endpoint Analysis — CRITICAL FINDING

### Old Endpoint: `?r=remote/search`

Returns **HTTP 404** for all category queries (6, 7, 28). The endpoint has been **removed** from the DOM-SC API.

Example queried:
```
?r=remote/search&categoria=6&data_inicio=01/06/2026&data_fim=11/07/2026&com_metadados=1
```

### New Endpoint: `?r=remote/list`

Discovered from the API documentation page at `?r=site/page&view=integracao`.

| Aspect | Old API (`/search`) | New API (`/list`) |
|--------|--------------------|--------------------|
| Response container | `publicacoes` array | `result` array |
| Pagination | Unknown (not documented) | Native: `page` + `count` params |
| categoria type | Integer (6, 7, 28) | String ("Contrato", "Convenio") |
| Entity data | `orgao_cnpj`, `orgao_nome`, `municipio` | Not in list response |
| Metadados | Nested `metadados` object with `numero`, `valor` | Not in list response |
| Individual detail | Not available | `url_origem_api` field per publication |
| Auth required | Basic Auth + X-API-Key | Same auth model |

### New API Response Schema (`?r=remote/list`)

Parameters:
- `page` — page number
- `count` — items per page

Returns per item:
- `codigo` (integer) — publication code
- `titulo` (string) — publication title
- `categoria` (string) — category name (e.g., "Contrato", "Convenio")
- `data_publicacao` (string) — publication date (dd/mm/yyyy)
- `data_cadastro` (string) — registration date
- `url_origem_api` (string) — URL to individual publication detail
- `status` (string) — publication status

### Known Working Endpoints (from API docs)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `?r=remote/list` | GET | List publications (with pagination) |
| `?r=remote/status` | GET | Get publication status by `codigo` |
| `?r=remote/verify` | GET | Verify credentials |
| `?r=remote/create` | POST | Register new publication |
| `?r=remote/delete` | POST | Delete scheduled publication |

## 4. Pagination Support

The new API endpoint `?r=remote/list` natively supports pagination via `page` and `count` parameters. This is a **significant improvement** over the old endpoint which had no documented pagination.

| Parameter | Supported | Notes |
|-----------|-----------|-------|
| `page` | YES | Page number (1-based) |
| `count` | YES | Items per page (not tested for maximum) |

## 5. HTML Scraping Fallback Viability

| Endpoint | URL | Status | Details |
|----------|-----|--------|---------|
| public_search | `?r=site/publication/search` | FAIL (404) | Endpoint not found |
| advanced_search | `?r=site/advancedSearch` | FAIL (404) | Endpoint not found |

**Verdict:** The public search pages also return 404. However, the entity portal pages at `?r=site/portal&codigoEntidade=N` are accessible and contain publication lists per entity. The entity pages show entity name in the H1 title but do not expose CNPJ data in the HTML directly.

## 6. Entity Data Investigation

The entity portal (`?r=site/portal&codigoEntidade=N`) shows:
- Entity name in page title/H1 (e.g., "Prefeitura Municipal de Agrolândia")
- Publication categories (Portarias, Licitações, etc.)
- Searchable publications per entity
- **No CNPJ visible** in the HTML response

Since the new API list endpoint does not include `orgao_cnpj`, `orgao_nome`, or `municipio` directly, entity data extraction requires one of:
1. **Parse `url_origem_api`** — fetch individual publication pages to extract entity CNPJ/name
2. **Parse `titulo` field** — may contain entity reference text
3. **Cross-reference with entity portal** — match entity names from portal pages
4. **Use entity matching on titulo** — apply fuzzy matching on the titulo field at the DB level

## 7. Summary

| Metric | Value |
|--------|-------|
| Site online | YES |
| Old API (`/search`) | **404 — REMOVED** |
| New API (`/list`) | Available (requires credentials) |
| API docs available | YES |
| Credentials in env | NO (dev environment) |
| Pagination supported | YES (native, page+count) |
| HTML scraping fallback | NOT VIABLE (public search also 404) |
| Uncovered entities in DB | N/A (not sampled) |

## 8. Recommendations

- **[CRITICAL] Update crawler endpoint** from `?r=remote/search` to `?r=remote/list` — the old endpoint is permanently removed
- **[CRITICAL] Set DOM_SC credentials** in production env vars (`DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY`)
- **[HIGH] Implement native pagination** via `page` + `count` parameters (new API supports it)
- **[HIGH] Handle new response schema** — `result` array instead of `publicacoes`, string categoria instead of integer
- **[MEDIUM] Extract entity data from `url_origem_api`** — individual publication pages may contain CNPJ/entity info
- **[MEDIUM] Expand temporal window** to 180 days as planned
- **[LOW] Improve logging** by municipio/entity for coverage tracking

## 9. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| New API also lacks entity CNPJ data | Records without entity matching | Use titulo parsing + DB-level fuzzy matching |
| Auth tokens for new API different format | 401 on all requests | Verify credential format against API docs |
| Rate limiting on new API | Throttled responses | Implement backoff + delay between pages |
| `url_origem_api` requires separate auth | Individual page fetch fails | Test with valid credentials first |
