# Consolidacao de Codigo Duplicado — TD-3.2

**Data:** 2026-07-11
**Story:** TD-3.2 — Eliminar Codigo Duplicado
**Debitos:** TD-SYS-016, TD-SYS-002, TD-DB-16

## Resumo

Consolidacao de tres focos de duplicacao que aumentavam risco de manutencao
e comportamento divergente no sistema de crawlers.

---

## 1. TD-SYS-016: Duas Implementacoes de Crawler PNCP

### Situacao Anterior

| Caracteristica | Async BidsCrawler | Sync Adapter (pncp_crawler_adapter) |
|---|---|---|
| Arquivo | `scripts/crawl/bids_crawler.py` | `scripts/crawl/pncp_crawler_adapter.py` |
| Status | DEAD CODE | FUNCIONAL |
| Orquestrador | Independente (asyncio) | `monitor.py` (`importlib`) |
| HTTP Client | `AsyncPNCPClient` (httpx) | `urllib.request` (stdlib) |
| Depende de `ingestion/` package? | SIM (6 sub-modulos) | NAO |

### Auditoria (TD-0.2)

O `bids_crawler.py` importa de 6 sub-modulos do package `ingestion/` que nao
existe mais no codigo. Duas dependencias nao tem equivalente em lugar nenhum:

- `ingestion._base.crawler` (BaseCrawler ABC)
- `ingestion.metrics` (Prometheus metrics)

**Resultado:** Nao ha divergencia de resultados — o BidsCrawler esta inoperante.
O sync adapter e a unica implementacao funcional.

### Decisao

**Implementacao mantida:** `pncp_crawler_adapter.py` (sync adapter)

**Implementacao removida:** `bids_crawler.py` — marcado como DEPRECATED com
rollback plan documentado no cabecalho do arquivo.

### Rollback Plan

Para reativar o BidsCrawler no futuro:
1. Restaurar o package `ingestion/` com:
   - `ingestion._base.crawler` (BaseCrawler ABC + helpers: accumulate_stats,
     chunk_list, empty_run_stats)
   - `ingestion.metrics` (Prometheus metrics wrapper)
2. Ou refatorar para importar de `scripts.crawl.*` em vez de `ingestion.*`
3. Registrar em `orchestrator.py:module_map` como `"pncp": "bids_crawler"`

---

## 2. TD-SYS-002: DSN Default Duplicado

### Situacao Anterior

O DSN default `postgresql://postgres@127.0.0.1:5433/pncp_datalake` estava
duplicado em tres lugares:

| Arquivo | Linha | Forma |
|---|---|---|
| `monitor.py` | 47-50 | `os.getenv("LOCAL_DATALAKE_DSN", "postgresql://...")` |
| `orchestrator.py` | 26-29 | `os.getenv("LOCAL_DATALAKE_DSN", "postgresql://...")` |
| `config/settings.py` | 33 | `os.getenv("LOCAL_DATALAKE_DSN", "")` |

### Aplicado

- `config/settings.py` agora e a **fonte unica de verdade** com o default
  `postgresql://postgres@127.0.0.1:5433/pncp_datalake`
- `monitor.py` importa `DEFAULT_DSN` de `config.settings`
- `orchestrator.py` importa `DEFAULT_DSN` de `config.settings`
- Nenhum modulo redefine o DSN localmente

### Arquivos Modificados

- `config/settings.py` — adicionado DEFAULT_DSN com default
- `scripts/crawl/monitor.py` — importa de settings, removeu definicao local
- `scripts/crawl/orchestrator.py` — importa de settings, removeu definicao local

---

## 3. TD-DB-16: Duas Funcoes de Upsert de Contratos

### Situacao Anterior

O debito mencionava duas funcoes de upsert para `pncp_supplier_contracts`:
uma row-by-row (lenta) e uma set-based (rapida).

### Auditoria

A funcao `upsert_pncp_supplier_contracts` em `db/migrations/006_upsert_rpcs.sql`
ja utiliza processamento set-based (JSONB array com INSERT ON CONFLICT).
Nao foi encontrada implementacao Python row-by-row ativa — a orquestracao
via `orchestrator.py` ja chama a SQL function diretamente com batch JSON.

### Decisao

- A funcao set-based em `006_upsert_rpcs.sql` e a **unica implementacao ativa**
- Adicionado comentario de consolidacao no cabecalho do arquivo SQL
- A funcao row-by-row esta **DEPRECATED** (se existiu, foi removida antes
  desta auditoria)

---

## 4. Common Module — `scripts/crawl/common.py`

### Funcionalidades Consolidadas

Para eliminar duplicacao de funcoes utilitarias entre crawlers, foi criado
o modulo `scripts/crawl/common.py` com as seguintes funcoes:

| Funcao | Descricao | Originalmente em |
|---|---|---|
| `digits_only(s)` | Remove todos os caracteres nao-digitos | contracts_crawler, dom_sc_crawler, doe_sc_crawler, sc_compras_crawler |
| `parse_date(v)` | Parseia datas em formato ISO, BR, datetime | dom_sc_crawler, doe_sc_crawler |
| `safe_float(v)` | Parseia numeros com suporte a formato BR | dom_sc_crawler, doe_sc_crawler |
| `safe_date(v)` | Extrai data ISO de date/datetime/string | pncp_crawler_adapter, contracts_crawler |
| `extract_cnpj(t)` | Extrai CNPJ de texto | doe_sc_crawler |
| `trunc(s, max)` | Trunca string com ellipsis | contracts_crawler |
| `generate_content_hash(r, fields)` | Hash MD5 deterministico para dedup | pncp_adapter, dom_sc, doe_sc, pcp, compras_gov |

### Crawlers Atualizados

| Crawler | Funcoes Substituidas | Status |
|---|---|---|
| `contracts_crawler.py` | `digits_only`, `safe_date`, `safe_float`, `trunc` | OK |
| `dom_sc_crawler.py` | `digits_only`, `parse_date`, `safe_float` | OK |
| `doe_sc_crawler.py` | `digits_only`, `parse_date`, `safe_float`, `extract_cnpj` | OK |
| `sc_compras_crawler.py` | `digits_only` | OK |
| `pncp_crawler_adapter.py` | `safe_float`, `safe_date` (estavam aninhadas) | OK |
| `pcp_crawler.py` | `generate_content_hash` | OK |
| `compras_gov_crawler.py` | `generate_content_hash` | OK |

Nota: `_parse_date` do `pcp_crawler.py` foi mantida local porque lida com
timestamps em milissegundos (formato PCP v2), diferente do padrao ISO/BR.
`_generate_content_hash` do `dom_sc_crawler.py` e `doe_sc_crawler.py` foram
mantidas locais porque usam campos especificos de cada fonte.

---

## Testes

```text
174 passed, 1 failed (pre-existing, transparencia_crawler)
```

Nenhuma regression introduzida. Todos os testes dos crawlers modificados
passam. Foram criados dois novos arquivos de teste:

- `tests/test_crawler_pncp.py` — Testes para o adapter PNCP
- `tests/test_upsert_contracts.py` — Validacao de schema do upsert

---

## Arquivos Modificados

| Arquivo | Acao |
|---|---|
| `scripts/crawl/common.py` | CRIADO |
| `tests/test_crawler_pncp.py` | CRIADO |
| `tests/test_upsert_contracts.py` | CRIADO |
| `docs/td-001/dedup-consolidation.md` | CRIADO |
| `config/settings.py` | MODIFICADO (DEFAULT_DSN adicionado) |
| `scripts/crawl/monitor.py` | MODIFICADO (importa DEFAULT_DSN de settings) |
| `scripts/crawl/orchestrator.py` | MODIFICADO (importa DEFAULT_DSN de settings) |
| `scripts/crawl/contracts_crawler.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/dom_sc_crawler.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/doe_sc_crawler.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/sc_compras_crawler.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/pncp_crawler_adapter.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/pcp_crawler.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/compras_gov_crawler.py` | MODIFICADO (usa common helpers) |
| `scripts/crawl/bids_crawler.py` | MODIFICADO (header DEPRECATED) |
| `db/migrations/006_upsert_rpcs.sql` | MODIFICADO (comentario de consolidacao) |
| `tests/test_contracts_crawler.py` | MODIFICADO (refs atualizadas) |
