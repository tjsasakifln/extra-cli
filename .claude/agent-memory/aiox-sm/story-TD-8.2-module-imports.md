---
name: story-td-8.2-module-imports
description: "TD-8.2: Fix broken module imports — 37/127 Python files (29%) have ImportError due to 8 categories of missing modules (clients/, ingestion/, supabase_client, etc.)"
metadata:
  type: project
---

# Story TD-8.2: Fix Broken Module Imports

**Criada:** 2026-07-11 | **Epic:** EPIC-TD-003 | **Status:** Draft | **File:** `docs/stories/epics/epic-td-003-reversa-remediation/story-TD-8.2-fix-module-imports.md`

**Contexto:** Auditoria automatizada revelou que 37/127 arquivos Python (29%) tem imports quebrados em 8 categorias:

1. **clients/** package nunca criado — 30 imports em 4 arquivos crawl centrais (async_client, sync_client, _parallel_mixin, adapter)
2. **ingestion/** package nunca criado — 62 imports em 4 arquivos (bids_crawler, pncp_arp_crawler, pncp_pca_crawler, loader)
3. **supabase_client** module missing — 10 ocorrencias em 5 arquivos
4. Standalone missing modules (exceptions, middleware, rate_limiter, metrics, redis_pool, degradation) — 12 ocorrencias
5. Intel pipeline wrong import paths (intel-enrich.py: cost_estimator sem prefixo lib.) — 3 ocorrencias
6. Missing pip packages (rarfile, pymupdf4llm, pytesseract) — 3 ocorrencias
7. Deprecated module refs (pncp_client, report_schema, report_metrics) — 4 ocorrencias
8. Wrong constants import path (lib/cli_validation.py) — 5 ocorrencias

**Decisao:** Stubs minimos (classes/funcoes vazias) para todos os modulos faltantes, sem implementar logica de negocios. Deprecated modules documentados. Total estimado: 16h.

**Proximo passo:** @dev implementar via `*develop TD-8.2`
