# Story TD-8.2: Fix Broken Module Imports — Crawl, Ingestion, and Intel Pipeline

**Status:** Ready
**Epic:** EPIC-TD-003
**Executor:** @dev
**Quality Gate:** @qa
**Quality Gate Tools:** [python-import, pytest, ruff]
**Fase:** 4 — Module Import Fix
**Estimativa:** 16h
**Prioridade:** P1

## Description

**As a** desenvolvedor mantenedor da plataforma Extra Consultoria,
**I want** todos os 127 arquivos Python do projeto poderem ser importados sem `ImportError`,
**so that** o pipeline de crawl, o pipeline de inteligencia, e ferramentas de analise estatica (mypy, pylint, code intelligence) funcionem sem quebras de modulo.

## Business Value

A auditoria automatizada (executada durante a criacao desta story) revelou que **37 dos 127 arquivos Python (29%) contem imports quebrados** — referencias a modulos ou pacotes que simplesmente nao existem no codebase. Estes imports quebrados se dividem em 8 categorias:

1. **Pacote `clients/` nunca criado** — `_parallel_mixin.py`, `adapter.py`, `async_client.py`, `sync_client.py` foram refatorados para importar de `clients.pncp.*` e `clients.base.*`, mas o pacote `clients/` nunca foi implementado (30 imports quebrados em 4 arquivos). Estes 4 arquivos sao centrais para o funcionamento de TODOS os crawlers PNCP.

2. **Pacote `ingestion/` nunca criado** — `bids_crawler.py`, `pncp_arp_crawler.py`, `pncp_pca_crawler.py`, `loader.py` foram refatorados para importar de `ingestion._base.crawler`, `ingestion.checkpoint`, `ingestion.config`, `ingestion.loader`, `ingestion.metrics`, `ingestion.transformer`, mas o pacote `ingestion/` nunca foi implementado (62 imports quebrados em 4 arquivos).

3. **`supabase_client` module missing** — `checkpoint.py`, `enricher.py`, `loader.py`, `pncp_arp_crawler.py`, `pncp_pca_crawler.py` importam `get_supabase` e `sb_execute` de um modulo `supabase_client` que nao existe (10 ocorrencias).

4. **Standalone missing modules** — `async_client.py` e `sync_client.py` importam de `exceptions`, `middleware`, `rate_limiter`; `circuit_breaker.py` importa de `metrics`, `redis_pool`, `degradation`. Nenhum destes modulos existe no projeto.

5. **Intel pipeline wrong import paths** — `intel-enrich.py` importa `cost_estimator`, `bid_simulator`, `victory_profile` sem o prefixo `lib.`, enquanto os modulos estao em `scripts/lib/`. Outros arquivos do pipeline usam `lib.` corretamente, indicando erro de copia/colagem.

6. **Missing pip packages** — `intel-extract-docs.py` importa `rarfile`, `pymupdf4llm`, `pytesseract` que nao estao em `requirements.txt` nem instalados.

7. **Deprecated module references** — `bids_crawler.py` importa `from pncp_client import AsyncPNCPClient` (pncp_client foi deprecado por TD-3.2); `validate-report-data.py` importa de `report_schema` (inexistente); `generate-report-b2g.py` importa de `report_metrics` (inexistente).

8. **False positives (mesmo modulo, import path diferente)** — `scripts/lib/cli_validation.py` importa `from constants import ...` em vez de `from config.constants import ...`, e `config/constants.py` existe mas nao e resolvivel via import simples.

O resultado atual e que 4 modulos centrais do crawl (`async_client.py`, `sync_client.py`, `circuit_breaker.py`, `bids_crawler.py`) nao podem ser importados em contexto nenhum, bloqueando analise estatica, testes, e ferramentas de code intelligence.

## Import Audit Summary

Auditoria executada em 2026-07-11 via script Python que varreu todos os 127 arquivos `.py` do projeto, analisou todos os `import` e `from ... import`, e resolveu cada import contra: stdlib, installed pip packages, e modulos locais do projeto.

### Top-Level Broken Imports (bloqueiam import do arquivo)

| File | Missing Modules | Severity |
|------|----------------|----------|
| `scripts/crawl/async_client.py` | `clients`, `exceptions`, `middleware` | CRITICAL |
| `scripts/crawl/sync_client.py` | `clients`, `exceptions`, `middleware` | CRITICAL |
| `scripts/crawl/_parallel_mixin.py` | `clients` | CRITICAL |
| `scripts/crawl/adapter.py` | `clients` | CRITICAL |
| `scripts/crawl/bids_crawler.py` | `ingestion`, `pncp_client` | CRITICAL |
| `scripts/crawl/pncp_arp_crawler.py` | `ingestion`, `supabase_client` | CRITICAL |
| `scripts/crawl/pncp_pca_crawler.py` | `ingestion`, `supabase_client` | CRITICAL |
| `scripts/crawl/checkpoint.py` | `supabase_client` | CRITICAL |
| `scripts/crawl/enricher.py` | `supabase_client` | CRITICAL |
| `scripts/crawl/loader.py` | `ingestion`, `supabase_client` | CRITICAL |
| `scripts/crawl/circuit_breaker.py` | `metrics` | CRITICAL |

### Lazy Broken Imports (falham em tempo de execucao, nao no import)

| File | Missing Modules | Callsite |
|------|----------------|----------|
| `scripts/crawl/circuit_breaker.py` | `redis_pool`, `degradation` | lines 245, 452 |
| `scripts/crawl/adapter.py` | `clients.base`, `clients.pncp.async_client` | lines 52, 74, 81, 215 |
| `scripts/crawl/_parallel_mixin.py` | `clients.pncp.async_client` | line 239 |

### Wrong Import Path (arquivos existem mas em local diferente)

| File | Wrong Import | Correct Import |
|------|-------------|----------------|
| `scripts/intel-enrich.py` | `from cost_estimator import ...` | `from lib.cost_estimator import ...` |
| `scripts/intel-enrich.py` | `from bid_simulator import ...` | `from lib.bid_simulator import ...` |
| `scripts/intel-enrich.py` | `from victory_profile import ...` | `from lib.victory_profile import ...` |
| `scripts/lib/cli_validation.py` | `from constants import ...` | `from config.constants import ...` |

### Missing pip packages

| Package | Used By | Status |
|---------|---------|--------|
| `rarfile` | `intel-extract-docs.py` | Not in requirements.txt |
| `pymupdf4llm` | `intel-extract-docs.py` | Not in requirements.txt |
| `pytesseract` | `intel-extract-docs.py` | Not in requirements.txt |

### Deprecated Module References

| File | Import | Deprecation Status |
|------|--------|-------------------|
| `scripts/crawl/bids_crawler.py` | `from pncp_client import AsyncPNCPClient` | Deprecated per TD-3.2 |
| `scripts/validate-report-data.py` | `from report_schema import ...` | Module never existed |
| `scripts/generate-report-b2g.py` | `from report_metrics import ...` | Module never existed |

## Acceptance Criteria

- [ ] AC1: `scripts/crawl/async_client.py` — todos os imports resolvem sem `ImportError` (dependencias: `clients.pncp.*`, `exceptions`, `middleware`)
- [ ] AC2: `scripts/crawl/sync_client.py` — todos os imports resolvem sem `ImportError` (dependencias: `clients.pncp.*`, `exceptions`, `middleware`)
- [ ] AC3: `scripts/crawl/_parallel_mixin.py` — todos os imports resolvem sem `ImportError` (dependencia: `clients.pncp.*`)
- [ ] AC4: `scripts/crawl/adapter.py` — todos os imports resolvem sem `ImportError` (dependencia: `clients.pncp.*`, `clients.base.*`)
- [ ] AC5: `scripts/crawl/bids_crawler.py` — todos os imports resolvem sem `ImportError` (dependencias: `ingestion.*`, `pncp_client`). Deprecation status documentado.
- [ ] AC6: `scripts/crawl/pncp_arp_crawler.py` — todos os imports resolvem sem `ImportError` (dependencias: `ingestion.*`, `supabase_client`). Deprecation status documentado.
- [ ] AC7: `scripts/crawl/pncp_pca_crawler.py` — todos os imports resolvem sem `ImportError` (dependencias: `ingestion.*`, `supabase_client`). Deprecation status documentado.
- [ ] AC8: `scripts/crawl/checkpoint.py` — import de `supabase_client` resolvido sem `ImportError`
- [ ] AC9: `scripts/crawl/enricher.py` — import de `supabase_client` resolvido sem `ImportError`
- [ ] AC10: `scripts/crawl/loader.py` — imports de `ingestion.config` e `supabase_client` resolvidos sem `ImportError`
- [ ] AC11: `scripts/crawl/circuit_breaker.py` — imports de `metrics` resolvidos sem `ImportError`. Lazy imports (`redis_pool`, `degradation`) protegidos com `try/except ImportError`.
- [ ] AC12: `scripts/intel-enrich.py` — imports de `cost_estimator`, `bid_simulator`, `victory_profile` corrigidos para `from lib.* import ...`
- [ ] AC13: `scripts/lib/cli_validation.py` — import de `constants` corrigido para `from config.constants import ...`
- [ ] AC14: Missing pip packages documentados — `rarfile`, `pymupdf4llm`, `pytesseract` adicionados a `requirements.txt` (ou documentados como opcionais)
- [ ] AC15: `validate-report-data.py` e `generate-report-b2g.py` — imports quebrados documentados e protegidos com `try/except ImportError` quando apropriado
- [ ] AC16: Script de auditoria automatizada executa e confirma zero `ImportError` em todos os 127 arquivos
- [ ] AC17: `pytest` — todos os testes existentes continuam passando apos as correcoes
- [ ] AC18: `ruff check scripts/` — zero novos erros introduzidos

## Scope

### IN
- Criacao de stubs para `crawl/clients/` package (modulos `pncp/__init__.py`, `pncp/circuit_breaker.py`, `pncp/retry.py`, `pncp/async_client.py`, `pncp/_parallel_mixin.py`, `base/__init__.py`, `base.py`)
- Criacao de stubs para `crawl/ingestion/` package (modulos `_base/crawler.py`, `checkpoint.py`, `config.py`, `loader.py`, `metrics.py`, `transformer.py`)
- Criacao de `supabase_client.py` stub em `scripts/crawl/supabase_client.py` ou `scripts/supabase_client.py`
- Criacao de stubs para `exceptions.py`, `middleware.py`, `rate_limiter.py`, `metrics.py`, `redis_pool.py`, `degradation.py` em `scripts/crawl/`
- Correcao de import paths em `intel-enrich.py` (adicionar prefixo `lib.`)
- Correcao de import paths em `lib/cli_validation.py` (usar `config.constants`)
- Documentacao de deprecation para `bids_crawler.py`, `pncp_arp_crawler.py`, `pncp_pca_crawler.py`
- Adicao de `rarfile`, `pymupdf4llm`, `pytesseract` em `requirements.txt`
- Protecao de lazy imports com `try/except ImportError`
- Script de verificacao automatizada de imports

### OUT
- Implementacao completa dos modulos `clients/`, `ingestion/` ou `supabase_client` — apenas stubs minimos (classes vazias, funcoes com `raise NotImplementedError`)
- Refatoracao de logica de negocios dos crawlers
- Renomeacao de modulos ou arquivos
- Correcao de outros problemas estruturais identificados pelo Reversa (ja cobertos por TD-8.1 e epics futuros)
- Implementacao de funcionalidades novas
- Instalacao de `rarfile`, `pymupdf4llm`, `pytesseract` no ambiente de producao

## Root Cause Analysis

Fonte: Auditoria automatizada de imports executada em 2026-07-11.

**Causa raiz do `clients/` package:** Os modulos `async_client.py`, `sync_client.py`, `adapter.py`, `_parallel_mixin.py` foram extraidos de um unico arquivo grande e refatorados para importar de um pacote `clients.pncp.*` que nunca foi implementado. O docstring de `_parallel_mixin.py` confirma: "Extracted from async_client.py to keep each file under 700 LOC." A extracao foi feita presumindo que o pacote `clients/` existiria em `scripts/crawl/clients/`, mas ele nunca foi criado.

**Causa raiz do `ingestion/` package:** Similar ao `clients/`, os crawlers foram refatorados para usar uma camada de "ingestion framework" (`ingestion._base.crawler`, `ingestion.checkpoint`, `ingestion.config`, `ingestion.loader`, `ingestion.metrics`, `ingestion.transformer`) que nunca foi implementada. O modulo `bids_crawler.py` e o principal usuario, com 25 imports do `ingestion` package.

**Causa raiz do `supabase_client`:** Provavelmente parte da mesma refatoracao — as funcoes `get_supabase()` e `sb_execute()` existiam em outro modulo ou seriam criadas em `supabase_client.py`, mas o arquivo nunca foi gerado.

**Causa raiz dos imports sem `lib.` prefix:** `intel-enrich.py` foi copiado de um template ou de outro script que usava `from cost_estimator import ...`, mas o modulo `cost_estimator` foi movido para `scripts/lib/` posteriormente. O `intel-collect.py` usa `from lib.cli_validation import ...` corretamente, indicando que `intel-enrich.py` simplesmente nao foi atualizado.

## Tasks / Subtasks

### Task 1: Criar stubs para `clients/` package (AC1-AC4)

Criar `scripts/crawl/clients/` com a estrutura que os modulos esperam:

- [ ] Task 1.1: Criar `scripts/crawl/clients/__init__.py` (vazio)
- [ ] Task 1.2: Criar `scripts/crawl/clients/base/__init__.py` e `scripts/crawl/clients/base.py` com stubs de `SourceCapability`, `SourceMetadata`, `SourceStatus`, `UnifiedProcurement`
- [ ] Task 1.3: Criar `scripts/crawl/clients/pncp/__init__.py`
- [ ] Task 1.4: Criar `scripts/crawl/clients/pncp/async_client.py` com stubs de `AsyncPNCPClient`, `STATUS_PNCP_MAP`, `PNCPDegradedError`
- [ ] Task 1.5: Criar `scripts/crawl/clients/pncp/circuit_breaker.py` com stub de `_circuit_breaker`
- [ ] Task 1.6: Criar `scripts/crawl/clients/pncp/retry.py` com stubs de `DateFormat`, `ModalityFetchState`, `ParallelFetchResult`, `UFS_BY_POPULATION`, `_get_format_rotation`, `_handle_422_response`, `_set_cached_date_format`, `_validate_date_params`, `calculate_delay`, `format_date`
- [ ] Task 1.7: Criar `scripts/crawl/clients/pncp/_parallel_mixin.py` com stub de `_PNCPParallelMixin`, `STATUS_PNCP_MAP`
- [ ] Task 1.8: Verificar que `import scripts.crawl.async_client` funciona sem erro

### Task 2: Criar stubs para `ingestion/` package (AC5-AC7, AC10)

Criar `scripts/crawl/ingestion/` com a estrutura esperada:

- [ ] Task 2.1: Criar `scripts/crawl/ingestion/__init__.py`
- [ ] Task 2.2: Criar `scripts/crawl/ingestion/_base/__init__.py` e `scripts/crawl/ingestion/_base/crawler.py` com stubs de `BaseCrawler`, `CrawlerResult`, `accumulate_stats`, `chunk_list`, `empty_run_stats`
- [ ] Task 2.3: Criar `scripts/crawl/ingestion/checkpoint.py` com stubs de `complete_ingestion_run`, `create_ingestion_run`, `get_last_checkpoint`, `mark_checkpoint_failed`, `save_checkpoint`
- [ ] Task 2.4: Criar `scripts/crawl/ingestion/config.py` com stubs de todas as constantes `INGESTION_*` (backfill, batch, delay, UFs, paginas, modalidades, ARP, PCA, upsert)
- [ ] Task 2.5: Criar `scripts/crawl/ingestion/loader.py` com stubs de `bulk_upsert`, `purge_old_bids`
- [ ] Task 2.6: Criar `scripts/crawl/ingestion/metrics.py` com stubs de todas as constantes `INGESTION_*` (pages, records, duration, UFs) e `ARP_*`, `PCA_*`
- [ ] Task 2.7: Criar `scripts/crawl/ingestion/transformer.py` com stub de `transform_batch`
- [ ] Task 2.8: Verificar que `import scripts.crawl.bids_crawler` funciona sem erro

### Task 3: Criar stubs para `supabase_client` e modulos avulsos (AC8-AC11)

- [ ] Task 3.1: Criar `scripts/crawl/supabase_client.py` com stubs de `get_supabase()`, `sb_execute()`
- [ ] Task 3.2: Criar `scripts/crawl/exceptions.py` com stubs de `PNCPAPIError`, `PNCPRateLimitError`
- [ ] Task 3.3: Criar `scripts/crawl/middleware.py` com stub de `request_id_var`
- [ ] Task 3.4: Criar `scripts/crawl/rate_limiter.py` com stub de `pncp_rate_limiter`
- [ ] Task 3.5: Criar `scripts/crawl/metrics.py` com stubs de `CB_OPEN_DURATION`, `CB_STATE_GAUGE`, `CIRCUIT_BREAKER_STATE`
- [ ] Task 3.6: Criar `scripts/crawl/redis_pool.py` com stub de `get_redis_pool`
- [ ] Task 3.7: Criar `scripts/crawl/degradation.py` com stub de `track_degradation`
- [ ] Task 3.8: Verificar que `import scripts.crawl.circuit_breaker` funciona sem erro
- [ ] Task 3.9: Verificar que `import scripts.crawl.checkpoint` funciona sem erro
- [ ] Task 3.10: Verificar que `import scripts.crawl.enricher` funciona sem erro

### Task 4: Corrigir import paths (AC12-AC13)

- [ ] Task 4.1: Em `scripts/intel-enrich.py`, alterar `from cost_estimator import ...` para `from lib.cost_estimator import ...`
- [ ] Task 4.2: Em `scripts/intel-enrich.py`, alterar `from bid_simulator import ...` para `from lib.bid_simulator import ...`
- [ ] Task 4.3: Em `scripts/intel-enrich.py`, alterar `from victory_profile import ...` para `from lib.victory_profile import ...`
- [ ] Task 4.4: Em `scripts/lib/cli_validation.py`, alterar `from constants import ...` para `from config.constants import ...`
- [ ] Task 4.5: Verificar que `python -c "import scripts.intel_enrich"` funciona sem erro

### Task 5: Missing pip packages e deprecation docs (AC14-AC15)

- [ ] Task 5.1: Adicionar `rarfile>=4.0` ao `requirements.txt` (opcional, comentado se for extra)
- [ ] Task 5.2: Adicionar `pymupdf4llm>=0.1.0` ao `requirements.txt`
- [ ] Task 5.3: Adicionar `pytesseract>=0.3.10` ao `requirements.txt`
- [ ] Task 5.4: Em `scripts/crawl/bids_crawler.py`, adicionar docstring de deprecation: "DEPRECATED: Use pncp_crawler.py via monitor.py em vez de import direto. pncp_client foi deprecado por TD-3.2."
- [ ] Task 5.5: Em `scripts/crawl/pncp_arp_crawler.py`, adicionar docstring de deprecation: "DEPRECATED: ARP crawling integrado ao pncp_crawler.py. Este modulo sera removido apos migracao completa."
- [ ] Task 5.6: Em `scripts/crawl/pncp_pca_crawler.py`, adicionar docstring de deprecation: "DEPRECATED: PCA crawling integrado ao pncp_crawler.py. Este modulo sera removido apos migracao completa."
- [ ] Task 5.7: Em `scripts/validate-report-data.py`, adicionar `try/except ImportError` para `report_schema` com fallback
- [ ] Task 5.8: Em `scripts/generate-report-b2g.py`, adicionar `try/except ImportError` para `report_metrics` com fallback

### Task 6: Script de verificacao e validacao final (AC16-AC18)

- [ ] Task 6.1: Criar `scripts/check_imports.py` que tenta importar cada um dos 127 arquivos e reporta falhas
- [ ] Task 6.2: Executar `python scripts/check_imports.py` — confirmar zero `ImportError`
- [ ] Task 6.3: Executar `pytest` — confirmar zero regressoes (AC17)
- [ ] Task 6.4: Executar `ruff check scripts/` — confirmar zero novos erros (AC18)
- [ ] Task 6.5: Executar `ruff format --check scripts/` — confirmar formatacao consistente

## Dev Notes

### Estrutura de Stubs

**Principio:** Criar stubs minimos que permitam que os modulos sejam importados sem `ImportError`. Stubs NAO implementam logica de negocios. Classes stub herdam de `object` e tem metodos com `pass` ou `raise NotImplementedError`. Constantes stub tem valores dummy.

**Localizacao dos stubs (package `clients/`):**

```
scripts/crawl/clients/
  __init__.py
  base/
    __init__.py
    base.py            # SourceCapability, SourceMetadata, SourceStatus, UnifiedProcurement
  pncp/
    __init__.py
    _parallel_mixin.py # _PNCPParallelMixin (classe vazia)
    async_client.py    # AsyncPNCPClient, STATUS_PNCP_MAP, PNCPDegradedError
    circuit_breaker.py # _circuit_breaker (sentinel object)
    retry.py           # DateFormat, ModalityFetchState, ParallelFetchResult, UFS_BY_POPULATION
                       # _get_format_rotation, _handle_422_response, _set_cached_date_format
                       # _validate_date_params, calculate_delay, format_date
```

**Localizacao dos stubs (package `ingestion/`):**

```
scripts/crawl/ingestion/
  __init__.py
  _base/
    __init__.py
    crawler.py          # BaseCrawler, CrawlerResult, accumulate_stats, chunk_list, empty_run_stats
  checkpoint.py         # complete_ingestion_run, create_ingestion_run, get_last_checkpoint,
                        # mark_checkpoint_failed, save_checkpoint
  config.py             # INGESTION_BACKFILL_CHUNK_DAYS, INGESTION_BACKFILL_DAYS,
                        # INGESTION_BATCH_DELAY_S, INGESTION_BATCH_SIZE_UFS,
                        # INGESTION_CONCURRENT_UFS, INGESTION_DATE_RANGE_DAYS,
                        # INGESTION_INCREMENTAL_DAYS, INGESTION_MAX_PAGES,
                        # INGESTION_MODALIDADES, INGESTION_PURGE_GRACE_DAYS, INGESTION_UFS,
                        # INGESTION_UPSERT_BATCH_SIZE, INGESTION_ARP_DAYS, INGESTION_ARP_ENABLED,
                        # INGESTION_ARP_MAX_PAGES, INGESTION_PCA_ENABLED, INGESTION_PCA_MAX_PAGES
  loader.py             # bulk_upsert, purge_old_bids
  metrics.py            # INGESTION_PAGES_FETCHED, INGESTION_RECORDS_FETCHED,
                        # INGESTION_RECORDS_UPSERTED, INGESTION_RUN_DURATION,
                        # INGESTION_UFS_FAILED, INGESTION_UFS_PROCESSED,
                        # ARP_PAGES_FETCHED, ARP_RECORDS_FETCHED, ARP_RECORDS_UPSERTED,
                        # ARP_RUN_DURATION, ARP_RUNS_TOTAL,
                        # PCA_PAGES_FETCHED, PCA_RECORDS_FETCHED, PCA_RECORDS_UPSERTED,
                        # PCA_RUN_DURATION, PCA_RUNS_TOTAL
  transformer.py        # transform_batch
```

**Localizacao dos stubs (modulos avulsos em `scripts/crawl/`):**

```
scripts/crawl/
  supabase_client.py    # get_supabase(), sb_execute()
  exceptions.py         # PNCPAPIError(Exception), PNCPRateLimitError(PNCPAPIError)
  middleware.py         # request_id_var (contextvars.ContextVar)
  rate_limiter.py       # pncp_rate_limiter (sentinel ou classe vazia)
  metrics.py            # CB_OPEN_DURATION, CB_STATE_GAUGE, CIRCUIT_BREAKER_STATE (Prometheus)
  redis_pool.py         # get_redis_pool()
  degradation.py        # track_degradation()
```

### Nota sobre modulos que ja existem

Os seguintes modulos foram reportados como "broken" pela auditoria automatizada mas NAO requerem correcao porque o import funciona em runtime (quando o script e executado de `scripts/`):
- `from datalake_helper import ...` — `scripts/datalake_helper.py` existe
- `from intel_sector_loader import ...` — `scripts/intel_sector_loader.py` existe
- `from report_dedup import ...` — `scripts/report_dedup.py` existe
- `from auditor_deterministic_checks import ...` — `scripts/auditor_deterministic_checks.py` existe
- `from lib.* import ...` — `scripts/lib/` package existe
- `from rapidfuzz import fuzz` — `rapidfuzz>=3.0.0` esta em `requirements.txt`

### Nota sobre lazy imports

`scripts/crawl/circuit_breaker.py` tem imports lazy (dentro de funcoes):
- `from redis_pool import get_redis_pool` (linha 245) — protegido com `try/except ImportError`? Verificar. Se nao, adicionar protecao.
- `from degradation import track_degradation` (linha 452) — mesma verificacao.
- `import sentry_sdk` (linhas 96, 141) — verificar se `sentry_sdk` esta em `requirements.txt`.

### Nota sobre pncp_client deprecation

O modulo `bids_crawler.py` importa `from pncp_client import AsyncPNCPClient`. Segundo TD-3.2, `pncp_client` foi deprecado em favor de `scripts/crawl/pncp_crawler.py`. O stub para `pncp_client` deve ser criado para nao quebrar o import, mas o modulo deve ser marcado como deprecated.

### Referencias

- Auditoria de imports: executada via script Python em 2026-07-11
- `_reversa_sdd/inventory.md` — estrutura do projeto
- `_reversa_sdd/dependencies.md` — dependencias
- TD-3.2: deprecacao de pncp_client (`docs/stories/td-3.2-pncp-resilience.md`)
- TD-8.1: cleanup previo de scripts duplicados (`docs/stories/epics/epic-td-003-reversa-remediation/story-TD-8.1-reversa-cleanup.md`)
- EPIC-TD-003: epic completo

## Testing

### Abordagem de Testes

- **Teste de import**: Script `scripts/check_imports.py` que tenta importar cada arquivo Python individualmente e reporta falhas
- **Testes existentes**: `pytest` deve continuar passando sem regressoes
- **Lint**: `ruff check scripts/` sem novos erros

### Cenarios de Teste

| Cenario | Entrada | Resultado Esperado |
|---------|---------|-------------------|
| Import async_client | `python -c "import scripts.crawl.async_client"` | Sucesso |
| Import sync_client | `python -c "import scripts.crawl.sync_client"` | Sucesso |
| Import bids_crawler | `python -c "import scripts.crawl.bids_crawler"` | Sucesso |
| Import circuit_breaker | `python -c "import scripts.crawl.circuit_breaker"` | Sucesso |
| Import intel_enrich | `python -c "import scripts.intel_enrich"` | Sucesso |
| Import lib.cli_validation | `python -c "from scripts.lib import cli_validation"` | Sucesso |
| Todos os imports | `python scripts/check_imports.py` | Zero falhas |
| Testes existentes | `pytest` | Zero falhas |
| Lint | `ruff check scripts/` | Zero novos erros |

## CodeRabbit Integration

> **CodeRabbit Integration**: Disabled
>
> CodeRabbit CLI is not enabled in `core-config.yaml`.
> Quality validation will use manual review process only.
> To enable, set `coderabbit_integration.enabled: true` in core-config.yaml

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-07-11 | 1.0 | Criacao inicial da story apos auditoria de imports | @sm (River) |
| 2026-07-11 | 1.1 | Validacao PO: GO 10/10 (concern AC13 documentado). Status Draft -> Ready. | @po (Pax) |
