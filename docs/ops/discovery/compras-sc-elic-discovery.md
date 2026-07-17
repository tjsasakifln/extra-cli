# Discovery — Compras SC · E-Lic · PNCP · Comprasnet Contratos

**Probed at:** 2026-07-17 (UTC)  
**Agent:** Subagent F+H  
**UA:** `Extra-Consultoria/1.0 (consultoria-licitacoes; +https://extraconsultoria.com.br)`  
**Rules:** timeout 20s, sleep between requests, no captcha bypass, no secrets.

Machine-readable twin: [`compras-sc-elic-discovery.json`](./compras-sc-elic-discovery.json)

---

## Summary table

| Source | Public JSON? | Auth | Primary endpoint | Adapter | Crawl-ready? |
|--------|--------------|------|------------------|---------|--------------|
| **Portal Compras SC** | Yes | Anonymous | `GET /api/editais?ano=YYYY` | `scripts/crawl/sc_compras_crawler.py` | **Yes** |
| **E-Lic SC** | No | Session/ASMX | HTML Mural + `Servicos.asmx` | `scripts/crawl/elic_sc_stub.py` | **No** (HTML/ASMX only) |
| **PNCP contratos** | Yes | Anonymous | `GET /api/consulta/v1/contratos` | `contracts_crawler.py` + `smoke_pncp_public.py` | **Yes** |
| **Comprasnet Contratos** | Partial | JWT Bearer (v1 bulk); catalog public | OpenAPI at `/docs` | none | **No** (needs credentials) |

---

## 1. Portal Compras SC — `https://compras.sc.gov.br/`

### Surface
- React SPA shell (Vite hashed assets, e.g. `/js/index.DaEEVxkq.js`).
- Backend JSON under `/api/*` (Spring-style 404 JSON bodies).

### Confirmed public endpoints

| Method | URL | Notes |
|--------|-----|-------|
| GET | `/api/editais?ano={YYYY}` | **Required `ano`**. Returns `{conteudo, pagina, porPagina, totalPaginas, totalElementos}`. |
| GET | `/api/editais/{id}` | Detail: modalidade, datas, `linkArquivosFTP`, etc. |

### Evidence (live)
- Without `ano` → **400** `Parâmetro ano é obrigatório.`
- `ano=2026` → **200**, `totalElementos=2602`, list item keys: `id, processo, tipo, orgaoSigla, orgaoNome, objeto, entregaProposta, abertura, situacao`.
- `tamanhoPagina` / `pagina` appear **ignored** (full year payload ~1.3MB returned even with `tamanhoPagina=1`).
- Detail `id=41624` → **200** with publication/modalidade fields.

### Adapter
Existing `sc_compras_crawler.py` already uses this JSON API (not HTML scrape).  
Smoke: `python -m scripts.crawl.sc_compras_crawler smoke` or `smoke()`.

---

## 2. E-Lic SC — `https://e-lic.sc.gov.br/`

### Surface
- ASP.NET (`Default.aspx`), Microsoft-IIS, Paradigma portal, Kendo UI, AjaxPro.
- CSP references Power BI / `login.e-lic.sc.gov.br` / `*.paradigmabs.com.br`.
- Homepage captcha: **not** observed on public landing (login UI present).

### What is public
| Resource | Status | Notes |
|----------|--------|-------|
| `/Default.aspx` | 200 HTML | Portal shell + ViewState |
| `/portal/Mural.aspx` | 200 HTML (~413KB) | Public mural content |
| `Portal/WebService/Servicos.asmx/*` | mixed | Methods referenced in page JS |

### ASMX methods referenced in HTML
- `PesquisarProcessos`
- `PesquisaPainelEletronico` / `PesquisaPainelEletronicoModuloModalidade`
- `PesquisarAlertaPublico`
- `AdicionarCookieAlerta`

### Probe results (non-aggressive GET only)
- `Servicos.asmx` / `?WSDL` → 302 to error page (no public WSDL browse).
- `PesquisarProcessos` GET → 500 “method name is not valid” (expects proper ASMX POST).
- `PesquisaPainelEletronico` GET → 500 missing `bFlMultiMoeda`.
- `PesquisarAlertaPublico` GET → 200 XML `RetornoAjax` with application error body.
- `/api` → **403**.

### Limitation
**No anonymous open JSON API** suitable for bulk edital/contract crawl.  
Do **not** reverse-engineer session ASMX for production ingestion without explicit product decision. Prefer **Compras SC JSON** + **PNCP** for SC coverage.

Selector map stub + structure contract: `scripts/crawl/elic_sc_stub.py` + fixture test.

---

## 3. PNCP — `https://pncp.gov.br/api/consulta/v1`

### Confirmed
| Endpoint | Auth | Min page size | Evidence |
|----------|------|---------------|----------|
| `/contratos` | Anonymous GET | invalid at 1; **10+ works**; 50/100/500 OK | 200 + `totalRegistros` in date window |
| `/contratacoes/publicacao` | Anonymous GET | **≥ 10** | 200 with `codigoModalidadeContratacao` |

### Contract item UF
- Primary: `unidadeOrgao.ufSigla` (e.g. `CE` in sample).
- Client filter: `transform_with_uf_filter()` / `uf_from_unidade()` — **never default to SC**.

### Smoke
```bash
python scripts/crawl/smoke_pncp_public.py
# writes docs/ops/discovery/pncp-smoke.json
```

Constants live in `contracts_crawler.CONTRACTS_BASE` (default `https://pncp.gov.br/api/consulta/v1`).

---

## 4. Comprasnet Contratos — `https://contratos.comprasnet.gov.br`

| Resource | URL | Status |
|----------|-----|--------|
| Swagger UI | `/api/docs` | 200 |
| OpenAPI 3.0 | `/docs` and `/docs/api-docs.json` | 200 (~418KB, 70 paths) |
| Title | API Contratos.gov.br v1.0 | |
| Auth scheme | `bearerAuth` JWT | `POST /api/v1/auth/login` |

### Anonymous vs authenticated
| Path | Without token |
|------|----------------|
| `/api/contrato/orgaos` | **200** public catalog |
| `/api/contrato/unidades` | **200** public catalog |
| `/api/contrato/{id}/…` legacy | often **200** `[]` |
| `/api/v1/contrato` and most `/api/v1/*` bulk | **401** `Authorization Token not found` |

**Conclusion:** useful open catalog endpoints exist; **bulk contract payload requires JWT**. Not a free anonymous substitute for PNCP `/contratos`.

---

## Recommendations

1. **Keep using** Compras SC `/api/editais` + PNCP `/contratos` as primary public feeds.
2. **E-Lic:** document-only / stub; no production crawler until open data appears.
3. **Comprasnet:** only pursue after credentialed integration decision.
4. Always rate-limit; for SC list smoke use list-only (no per-item detail fan-out).
