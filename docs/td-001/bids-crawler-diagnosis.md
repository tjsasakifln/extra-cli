# Diagnostico: bids_crawler.py — Imports Quebrados

**Data:** 2026-07-11
**Autor:** @dev (Dex)
**Story:** TD-0.2
**Referencia:** TD-SYS-001 (CRITICAL) — Assessment tracker

## Resumo

O modulo `bids_crawler.py` importa de um package `ingestion/` que nao existe mais no codigo. O BidsCrawler async e suas funcoes modulares de suporte (`crawl_full`, `crawl_incremental`, `crawl_backfill`) estao inoperantes. O pipeline PNCP continua operacional via o sync adapter `pncp_crawler_adapter.py`, carregado pelo `monitor.py`.

## Crawlers PNCP: Duas Implementacoes

| Caracteristica | Async BidsCrawler | Sync Adapter (pncp_crawler_adapter) |
|---|---|---|
| **Arquivo** | `scripts/crawl/bids_crawler.py` | `scripts/crawl/pncp_crawler_adapter.py` |
| **Status** | DEAD CODE | FUNCIONAL |
| **Orquestrador** | Independente (via `asyncio`) | `monitor.py` (`crawl_source()` -> `_load_crawler()`) |
| **HTTP Client** | `AsyncPNCPClient` (httpx) | `urllib.request` (sincrono) |
| **Importa `ingestion/`?** | SIM — 6 sub-modulos | NAO |
| **Requires BaseCrawler ABC?** | SIM (`ingestion._base.crawler`) | NAO |
| **Requires Prometheus metrics?** | SIM (`ingestion.metrics`) | NAO |
| **Transformacao** | `transform_batch()` de `ingestion.transformer` | Propria (`_transform_record()`) |
| **Upsert** | `bulk_upsert()` de `ingestion.loader` | Atraves de `crawl_source()` em `monitor.py` |
| **Checkpoint** | `ingestion.checkpoint` | NAO (monitor.py usa `ingestion_runs` table) |
| **Config** | `ingestion.config` | Env vars locais no proprio modulo |

## Imports Quebrados em bids_crawler.py

O arquivo `bids_crawler.py` (linhas 34-70) importa de 6 sub-modulos do package `ingestion/`:

### 1. `ingestion._base.crawler` — NAO EXISTE
```
from ingestion._base.crawler import (
    BaseCrawler, CrawlerResult, accumulate_stats, chunk_list, empty_run_stats,
)
```
- Diretorio `_base/` nao existe em `scripts/crawl/` nem em nenhum outro lugar
- `BaseCrawler` e uma ABC (classe base abstrata) que precisaria ser criada
- `accum_stats`, `chunk_list`, `empty_run_stats` sao helpers utilitarios

### 2. `ingestion.config` — EXISTE como `scripts.crawl.config`
```
from ingestion.config import (
    INGESTION_BACKFILL_CHUNK_DAYS, INGESTION_BACKFILL_DAYS, ...
)
```
- O arquivo `scripts/crawl/config.py` contem todas essas constantes
- Apenas o caminho de import mudou de `ingestion.config` para `scripts.crawl.config`

### 3. `ingestion.transformer` — EXISTE como `scripts.crawl.transformer`
```
from ingestion.transformer import transform_batch
```
- `scripts/crawl/transformer.py` contem `transform_batch()` e `transform_pncp_item()`
- Mesmo caso: apenas o caminho de import mudou

### 4. `ingestion.loader` — EXISTE como `scripts.crawl.loader`
```
from ingestion.loader import bulk_upsert, purge_old_bids
```
- `scripts/crawl/loader.py` contem `bulk_upsert()` e `purge_old_bids()`
- Mas o proprio `loader.py` tambem importa de `ingestion.config` (linha 18)
- Dependencia circular de imports quebrados

### 5. `ingestion.checkpoint` — EXISTE como `scripts.crawl.checkpoint`
```
from ingestion.checkpoint import (
    get_last_checkpoint, save_checkpoint, mark_checkpoint_failed,
    create_ingestion_run, complete_ingestion_run,
)
```
- `scripts/crawl/checkpoint.py` contem todas essas funcoes
- Apenas o caminho de import mudou

### 6. `ingestion.metrics` — NAO EXISTE
```
from ingestion.metrics import (
    INGESTION_RECORDS_FETCHED, INGESTION_RECORDS_UPSERTED,
    INGESTION_UFS_PROCESSED, INGESTION_UFS_FAILED,
    INGESTION_PAGES_FETCHED, INGESTION_RUN_DURATION,
)
```
- Nao ha modulo de metrics Prometheus em lugar nenhum do codigo
- Seria necessario criar ou remover todas as referencias a Prometheus

## Outros Arquivos com Imports Quebrados de `ingestion/`

Fora de escopo desta story, mas documentado para TD-3.2:

| Arquivo | Import Quebrado | Impacto |
|---|---|---|
| `scripts/crawl/pncp_arp_crawler.py` | `ingestion._base.crawler`, `ingestion.config`, `ingestion.metrics` | ARP crawler inoperante |
| `scripts/crawl/pncp_pca_crawler.py` | `ingestion._base.crawler`, `ingestion.config`, `ingestion.metrics` | PCA crawler inoperante |
| `scripts/crawl/loader.py` | `ingestion.config` (INGESTION_UPSERT_BATCH_SIZE) | Usado pelo bids_crawler (dead code). Outros loaders (adapter) nao usam este loader. |

## Conclusao

### BidsCrawler: DEAD CODE

O `bids_crawler.py` nao e funcional porque:
1. Depende de `ingestion._base.crawler` (BaseCrawler ABC) — nao existe
2. Depende de `ingestion.metrics` (Prometheus) — nao existe
3. Demais imports poderiam ser corrigidos (apontando para `scripts.crawl.*`)
4. Recriar os modulos faltantes e refatorar os imports e trabalho significativo

**Decisao:** Marcar `bids_crawler.py` como dead code, preservar para referencia na consolidacao TD-3.2.

### Sync Adapter: FUNCIONAL

O `pncp_crawler_adapter.py` e funcional e auto-suficiente:
1. Nao depende de nenhum package externo alem de `urllib`, `hashlib`, `json`
2. E carregado dinamicamente por `monitor.py` via `importlib.import_module()`
3. Possui configuracao propria via env vars
4. Implementa crawl full e incremental com paginacao e retry
5. Implementa transformacao e filtro por keywords de engenharia

## Recomendacao para TD-3.2

1. **Consolidar** as duas implementacoes em uma unica, preferencialmente async (httpx)
2. **Criar** ou eliminar a necessidade de `ingestion._base.crawler` (ABC)
3. **Resolver** Prometheus metrics ou substituir por logging estruturado
4. **Corrigir** imports de `pncp_arp_crawler.py`, `pncp_pca_crawler.py`, `loader.py`
5. **Decidir** se o sync adapter sera mantido como fallback ou substituido

## Referencias

- **Story:** `docs/stories/epics/epic-td-001-resolution/story-TD-0.2-imports-quebrados.md`
- **Assessment:** TD-SYS-001 (CRITICAL) — Imports quebrados para `ingestion/` package
- **Epic:** `EPIC-TD-001` — Technical Debt Resolution
- **Arquivo diagnosticado:** `scripts/crawl/bids_crawler.py`
- **Arquivo funcional:** `scripts/crawl/pncp_crawler_adapter.py`
- **Orquestrador:** `scripts/crawl/monitor.py`
