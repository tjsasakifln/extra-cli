# DOE-SC Viability Research

## Summary

**Decision:** Build crawler with **credential-based REST API** (requires DOE_SC_LOGIN and DOE_SC_PASSWORD env vars). Fallback to scraping via PDF repository if API is unavailable.

## Investigation

### Source Identification
DOE-SC (Diario Oficial do Estado de Santa Catarina) is hosted at:

- **Old domain:** `doe.sea.sc.gov.br` — redirects to portal
- **Portal SPA:** `https://portal.doe.sea.sc.gov.br/v2.44.06/` (Angular SPA, PrimeNG)
- **API base:** `https://portal.doe.sea.sc.gov.br/apis/doe-api/`
- **PDF repo:** `https://portal.doe.sea.sc.gov.br/repositorio/`
- **PDF alternative:** `https://sigio2.doe.sea.sc.gov.br/sigio/Materias/{YYYYMMDD}/Jornal/{cdJornal}.pdf`
- **ALESC open data:** `https://data.alesc.sc.gov.br/` (not responding)

### API Endpoints Discovered

All endpoints at `https://portal.doe.sea.sc.gov.br/apis/doe-api/`:

| Endpoint | Method | Description | Needs Auth |
|----------|--------|-------------|------------|
| `/login` | POST | Authentication (login + password) | No |
| `/loginGov` | POST | Gov.br authentication | No |
| `/logout` | GET | Session logout | Yes |
| `/edicao` | GET | Newspaper editions list | Yes |
| `/edicao/buscar-jornal` | GET | Search journal by date | Yes |
| `/materia` | GET | Published matters list | Yes |
| `/materia/list` | GET | List all matters | Yes |
| `/categoria` | GET | Categories list | Yes |
| `/assunto` | GET | Subjects list | Yes |
| `/empresa` | GET | Companies/entities list | Yes |
| `/empresa/listAll` | GET | List all entities | Yes |
| `/noticia` | GET | News | Yes |
| `/dashboard` | GET | Dashboard data | Yes |
| `/report` | GET | Reports | Yes |

### Auth Pattern
- **Method:** Bearer token
- **Login:** POST `/login` with `{login: "CPF", password: "..."}` 
- **Token:** Returned by login, stored in localStorage as `doe-token`
- **Headers:** `Authorization: Bearer {token}` on all subsequent requests
- **Logout:** Clears token, calls `/logout`

### Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API requires subscription (authenticated) | Confirmed | Medium | Env vars for credentials |
| PDF repo accessible but requires session | High | Medium | Can proxy through API token |
| API rate limiting | Medium | Low | Implement backoff + delay |
| Source may require gov.br cert | Medium | Medium | Document alternative auth flow |

### Architecture Decision

**Decision:** Use REST API with Bearer token auth.

**Rationale:**
1. The API is well-structured (AdonisJS) with standard REST patterns
2. Pagination uses `page` and `perPage` params
3. Date filtering available via query params
4. The Angular SPA gives us visibility into the complete API surface
5. The crawler can be configured via env vars like the DOM-SC crawler

**Risk to mention to the product owner:** The DOE-SC is not a public/open-data API. It's a paid subscription system. Our crawler will require valid credentials. Without credentials, we can only access the PDF editions (if authorized). Currently the PDF repo returns 403.

**Alternative considered:** Scraping HTML/PDF only — rejected because:
1. PDF repo returns 403 without proper session
2. HTML scraping would require maintaining a Playwright-based crawler
3. The REST API is more reliable and structured
4. All discovered endpoints are well documented by the SPA bundle

### Data Available

The API provides structured data about:
- **Editions** (edicoes): Daily PDF editions of the state gazette
- **Matters** (materias): Individual publications/acts within each edition
- **Categories** (categorias): Types of publications
- **Subjects** (assuntos): Subject classification
- **Entities** (empresas): Publishing organizations (the 513 state entities)
- **Digital signatures** (assinatura-digital): Document validation

For procurement coverage, the relevant data is in the "materia" (matters) endpoint, which contains the text of each publication. These can be filtered by:
- Date range
- Category (licitacoes, contratos, editais)
- Organization (orgao publico)

## Setup Required

To use this crawler, set these environment variables:

```bash
export DOE_SC_LOGIN="12345678909"       # CPF with access
export DOE_SC_PASSWORD="your_password"   # Password
export DOE_SC_BASE="https://portal.doe.sea.sc.gov.br/apis/doe-api"
```

---

**Research conducted:** 2026-07-11
**Researcher:** Dex (Builder) / @dev
**Status:** Viability confirmed (with credential dependency)
