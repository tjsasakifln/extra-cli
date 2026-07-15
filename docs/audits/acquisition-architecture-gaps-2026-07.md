# Arquitetura de Aquisição — Gaps — 2026-07-15

Auditoria READ-ONLY realizada por Agente G na branch `epic-coverage-max-200km`.
Objetivo: revisar a arquitetura de aquisição de dados e identificar gaps que
impedem adicionar novas fontes sem duplicar infraestrutura.

---

## 1. Interfaces de Crawler (análise de consistência)

### Classes/Protocolos base encontrados

| Arquivo | Tipo | Obrigatoriedade |
|---------|------|----------------|
| `scripts/crawl/ingestion/_base/crawler.py` | `CrawlerProtocol` (Protocol) | Recomendado |
| `scripts/crawl/ingestion/_base/crawler.py` | `BaseCrawler` (alias `CrawlerProtocol` | Backward compat |
| `scripts/crawl/bids_crawler.py` | `BaseCrawler` (ABC `ingestion._base.crawler`) | DEPRECATED |
| `scripts/crawl/adapter.py` | `PNCPLegacyAdapter` (SourceAdapter) | Específico PNCP |
| `scripts/crawl/registry.py` | `SourceInfo` (dataclass) | Registry central |

### Quantas classes base diferentes?

**3 conceitos distintos:**

1. **`CrawlerProtocol`** (Protocol) — interface canônica atual, exige:
   - `crawl(mode: str) -> list[dict]` ou aceita `CrawlRequest`
   - `transform(records) -> list[dict]`
   - Módulos Python (não classes), exceto quando implementam o protocol

2. **`PNCPLegacyAdapter`** — implementa `SourceAdapter` (de `clients.base`) com:
   - `fetch(data_inicial, data_final, ufs) -> AsyncGenerator[UnifiedProcurement]`
   - `normalize(raw_record)` — vazio, `pass`
   - API orientada a datas, não a modo (`full`/`incremental`)

3. **`BidsCrawler`** (ABC `BaseCrawler`) — DEPRECATED, coexistiu até TD-3.2

### São consistentes?

**Nao.** Ha tres paradigmas convivendo:

- **Paradigma A** (monitor.py + pncp_crawler_adapter.py): modulo com `crawl()` / `transform()`, retorna `list[dict]`
- **Paradigma B** (adapter.py + AsyncPNCPClient): classe orientada a datas com `fetch()`, retorna `AsyncGenerator[UnifiedProcurement]`
- **Paradigma C** (bids_crawler.py, deprecated): classe ABC com `crawl()`/`transform()`, via `ingestion._base`

O registry (`registry.py`) resolve o mapeamento nome → modulo, mas o Protocol nao e
checado estaticamente — a verificacao ocorre em runtime via `@runtime_checkable` em
`_load_crawler()` no monitor.py.

### O que um novo crawler precisa implementar?

Depende de qual caminho ele segue:

| Caminho | O que implementar | Suportado por |
|---------|------------------|---------------|
| **Recomendado** | `crawl(mode) -> list[dict]` + `transform(records) -> list[dict]` | monitor.py, orchestrator.py |
| **Adapter** | Classe SourceAdapter com `fetch()`, `metadata`, `health_check()` | ConsolidationService |
| **BidsCrawler** | Classe BaseCrawler + `ingestion.*` package | DEPRECATED |

**GAP-1:** Um novo crawler precisa escolher entre interfaces sem documentacao clara
de qual e a canonica. O registry mapeia nome → modulo mas nao valida se o modulo
realmente implementa o Protocol.

**GAP-2:** `CrawlerProtocol` exige `crawl(mode: str) -> list[dict]`, mas
`monitor.py` ja suporta `CrawlRequest` como alternativa (`try/except TypeError`).
Isso e fragil e nao escalavel — cada novo crawler pode acabar no branch errado.

---

## 2. Raw Zone & Provenance

### Onde os dados brutos sao armazenados?

Nao ha uma "raw zone" separada. Os dados sao armazenados diretamente no PostgreSQL
via Supabase RPC:

- **Tabela:** `pncp_raw_bids` — dados transformados (nao raw)
- **Campo `raw_payload`:** coluna JSONB que preserva o payload original da API PNCP
- **Demais fontes (DOM-SC, PCP, etc.):** sem raw_payload — apenas colunas normalizadas

### Formato: JSON? CSV? DB direto?

DB direto via RPC (`upsert_pncp_raw_bids`). Formato intermediario: `list[dict]` em Python,
serializado como `jsonb` na chamada RPC.

### Provenance: cada registro sabe de onde veio?

Sim — coluna `source` (texto) identifica a fonte:
- `"pncp"` para PNCP
- `"dom_sc"` para DOM-SC
- `"pcp"` para PCP
- etc.

E ha coluna `crawl_batch_id` (opcional) para rastrear a execucao especifica.

**GAP-3:** Apenas o crawler PNCP preserva `raw_payload` (JSONB com resposta original).
Os demais crawlers perdem os dados brutos apos transformacao — impossivel re-processar
ou auditar o dado original sem re-fetch da API.

**GAP-4:** Nao ha data lake / cold storage. Dados mais velhos que 400 dias sao
purgeados (`purge_old_bids`) sem backup. Nao ha S3/GCS como raw zone definitiva.

---

## 3. Normalizacao Pipeline

### Pipeline atual

```
Raw API response (dict)
  → transform_pncp_item() | transform_batch()
    → pncp_raw_bids row (dict)
      → source overridden (crawler source tag)
        → upsert_pncp_raw_bids RPC (jsonb → SQL)
```

### Onde:

- **`scripts/crawl/transformer.py`**: `transform_pncp_item()` — mapeia campos PNCP
  para schema `pncp_raw_bids`. Usa SHA-256 para `content_hash` (mudanca incremental).
  Preserva `raw_payload` como JSONB.
- **`scripts/crawl/ingestion/transformer.py`**: STUB — implementacao vazia, apenas
  passa `records` direto. Marcado como "deferred".

### Mapeamento de campos

Hardcoded no `transform_pncp_item()`. Cada campo e extraido com fallbacks:
```python
uf = unidade.get("ufSigla") or raw_item.get("uf") or ""
municipio = unidade.get("municipioNome") or raw_item.get("municipioNome") or ""
```
Nao ha um schema mapping desacoplado (YAML/JSON) — tudo em codigo.

### Como um novo crawler adiciona seu schema?

**GAP-5:** Nao ha mecanismo de schema mapping extensivel. Um novo crawler precisa:
1. Editar `transformer.py` ou criar seu proprio transform
2. Garantir que o output case com a tabela `pncp_raw_bids`
3. Se precisar de colunas novas, criar migration + alter table

**GAP-6:** O pipeline raw → normalized → canonical **nao existe**. So ha
raw → normalized (unico passo). Nao ha camada canonical separada — `pncp_raw_bids`
e tanto o schema normalizado quanto o canonical.

**GAP-7:** `ingestion/transformer.py` e um stub que retorna os records sem
transformacao, mas o `bids_crawler.py` (deprecated) importava dele. A presenca
de stubs vivos no codigo-base confunde novos desenvolvedores.

---

## 4. Deduplicacao (algoritmo e pontos de falha)

### Dois algoritmos concorrentes

| Onde | Metodo | Campos | Algoritmo |
|------|--------|--------|-----------|
| `transformer.py:compute_content_hash()` | SHA-256 | `objeto_compra + valor_total_estimado + situacao_compra` | Change detection |
| `common.py:generate_content_hash()` | MD5 | `orgao_cnpj + objeto_compra + data_publicacao` (default) | Change detection |
| `async_client.py / _parallel_mixin.py` | Set dedup | `codigoCompra` ou `numeroControlePNCP` | In-memory dedup |

### Onde a dedup acontece?

1. **In-memory:** `_PNCPParallelMixin` usa `seen_ids: set[str]` para evitar duplicatas
   entre modalidades na mesma UF
2. **DB-level:** RPC `upsert_pncp_raw_bids` usa `ON CONFLICT (pncp_id) DO UPDATE` —
   a dedup primaria e por `pncp_id` (chave natural)
3. **Change detection:** `content_hash` SHA-256 evita writes desnecessarios quando
   o registro nao mudou (RPC retorna "unchanged" count)

### E deterministico?

- `compute_content_hash()`: **sim** — campos canonizados (lowercase + strip)
- `generate_content_hash()` em common.py: **sim** — MD5 deterministica
- Mas **os dois usam campos diferentes**, entao o mesmo registro pode ter hashes
  diferentes dependendo de qual funcao foi chamada.

### Funciona com multiplas fontes simultaneas?

**GAP-8:** A dedup primaria e por `pncp_id` — um ID do PNCP. Outras fontes
(PCP, ComprasGov, DOM-SC) tem IDs proprios. Um mesmo edital vindo de duas fontes
seria inserido como dois registros separados porque os IDs sao diferentes. Nao ha
dedup cross-source.

**GAP-9:** O `generate_content_hash()` em `common.py` existe como "centralizada"
mas **ninguem a chama** — cada crawler tem sua propria logica de hash. A funcao
foi criada pelo TD-3.2 para unificar mas nao foi adotada.

---

## 5. Idempotencia & Checkpoints

### UPSERT ou INSERT?

**UPSERT** via RPC `upsert_pncp_raw_bids`. Conflito por `pncp_id`.
Coluna `content_hash` permite detectar se o registro mudou (evita UPDATE desnecessario).

### Crawlers podem ser reexecutados sem duplicar?

**Sim — para PNCP.** O `ON CONFLICT (pncp_id) DO UPDATE` garante idempotencia a nivel
de linha. Para outras fontes, depende de terem `pncp_id` ou chave unica equivalente.

### Checkpoints: dois sistemas paralelos

| API | Uso | Tabela | Chave |
|-----|-----|--------|-------|
| `scripts/crawl/checkpoint.py` (sync) | orchestrator.py (psycopg2) | `ingestion_checkpoints` | `(source, scope_key)` |
| `scripts/crawl/checkpoint.py` (async) | bids_crawler.py (Supabase) | `ingestion_checkpoints` | `(source, uf, modalidade_id, crawl_batch_id)` |
| `scripts/crawl/ingestion/checkpoint.py` | STUB — nao implementado | — | — |

### Resume de onde parou?

**GAP-10:** O checkpoint e por `(source, scope_key)` com `last_date = CURRENT_DATE` —
apenas marca que a fonte foi processada hoje. **Nao ha checkpoint de pagina** para
crawlers paginados. Se um crawl de 200 paginas falhar na pagina 150, na proxima
execucao ele comeca da pagina 1, nao da 150.

**GAP-11:** `ingestion/checkpoint.py` e um STUB. Se alguem importar
`ingestion.checkpoint.get_last_checkpoint()`, recebe `None` sempre. Isso e
perigoso porque o codigo pode interpretar "None" como "nunca crawleado" e
iniciar um full crawl desnecessario.

---

## 6. Resiliencia (retry, circuit breaker, rate limit)

### Retry: `scripts/crawl/retry.py`

- `calculate_delay()`: exponential backoff com jitter ±50%
- Parametros via `config.RetryConfig`: `base_delay`, `exponential_base`, `max_delay`
- Usado em `async_client.py` e `pncp_crawler_adapter.py`
- `_handle_422_response()`: tratamento especial para erro 422 do PNCP
  (formato de data invalido), com fallback gracioso

### Circuit Breaker: `scripts/crawl/circuit_breaker.py`

- `PNCPCircuitBreaker`: in-memory, `asyncio.Lock`
- `RedisCircuitBreaker`: Redis-backed, compartilhado entre workers Gunicorn
- 5 instancias: `pncp`, `pcp`, `comprasgov`, `brasilapi`, `ibge`
- Half-open: `try_recover()` verifica se cooldown expirou
- Timeout configuravel por fonte

### Rate Limiter: `scripts/crawl/rate_limiter.py`

- `TokenBucketRateLimiter` — bucket de tokens
- Thread-safe (`threading.Lock`) e async (`async_check()`)
- Instancia global `pncp_rate_limiter` com **1 req/s**
- **GAP-12:** A instancia global unica nao permite rate limits diferentes por
  dominio. Todos os crawlers compartilham o mesmo token bucket de 1 req/s.
  Para crawlers de portais municipais (que aceitariam mais requisicoes), o
  gargalo e desnecessario.

### Middleware: `scripts/crawl/middleware.py`

- Apenas tracing (request_id via ContextVar) e timing
- **GAP-13:** Nao ha middleware pipeline real — sem logging estruturado automatico,
  sem metricas de latencia por request, sem hooks pre/post.

### Security: `scripts/crawl/security.py`

- `validate_url_scheme()`: SSRF defense
- `sanitize_url_param()`: URL encoding de parametros
- `USER_AGENT`: padronizado
- `SSL_VERIFY_ENABLED = True`: politica explicita

### Timeouts

- HTTP: 10s (enricher), 30s (pncp_crawler_adapter), 30s (IBGE municipios)
- Per-modality PNCP: 20s (configuravel)
- Per-UF PNCP: 90s normal, 120s degradado
- Cadeia validada em startup por `validate_timeout_chain()`

---

## 7. Execucao Concorrente

### `_PNCPParallelMixin` (`_parallel_mixin.py`)

- **Modelo: asyncio** com `asyncio.gather()`
- Semaphore por UF (max_concurrent = 10)
- Batching de UFs via `PNCP_BATCH_SIZE` + `PNCP_BATCH_DELAY_S`
- Timeout por modalidade (`asyncio.wait_for` com `per_modality_timeout`)
- Timeout por UF (`PER_UF_TIMEOUT`)
- Partial accumulation: se timeout ocorre com dados parciais, retorna o que tem

### `orchestrator.py` (DEPRECATED)

- **Modelo: sync** com psycopg2
- Sem async — cada fonte sequencial
- Chamado por scripts externos

### `monitor.py`

- **Modelo: sync** — chama `crawl_source()` para cada fonte sequencialmente
- Cada fonte individual pode ser async internamente (PNCP com asyncio),
  mas o monitor e sincrono entre fontes

### Lock contra execucao concorrente indevida?

**GAP-14:** Nao ha lock global. Nada impede duas instancias de `monitor.py`
rodando simultaneamente para fontes diferentes (ou mesma fonte). O checkpoint
de `(source, scope_key)` previne re-execucao no mesmo dia, mas e baseado em
data, nao em lock distribuido.

### Resource limiting

**GAP-15:** Nao ha limite de memoria configurado. Um crawl com `max_pages=200`
por UF × 27 UFs × 4 modalidades pode gerar centenas de milhares de registros em
memoria antes do upsert. Nao ha spill-to-disk nem chunking por contagem de
registros (apenas batch de UFs).

---

## 8. Metricas por Fonte

### O que e medido?

| Arquivo | Metricas declaradas | Status |
|---------|--------------------|--------|
| `scripts/crawl/metrics.py` | `CB_OPEN_DURATION`, `CB_STATE_GAUGE`, `CIRCUIT_BREAKER_STATE` | **STUB** (todos `None`) |
| `scripts/crawl/ingestion/metrics.py` | `INGESTION_*`, `ARP_*`, `PCA_*` (12 metricas) | **STUB** (todos `None`) |

### Como sao expostas?

**GAP-16:** As metricas nao sao expostas. Sao stubs que permitem o import nao
quebrar, mas `CB_OPEN_DURATION = None` significa que `circuit_breaker.py` tenta
`CB_STATE_GAUGE.labels(source=self.name).set(1)` — que quebraria se o codigo
chegasse la. Felizmente, `labels()` em `None` levanta `AttributeError` que e
capturado em `try/except` generico.

**GAP-17:** Nao ha endpoint Prometheus. Nao ha exportacao para APM (Datadog,
New Relic, etc.). As unicas metricas observaveis sao logs e `ingestion_runs`
no banco.

### O que e registrado no banco?

`ingestion_runs` armazena por execucao: source, status, fetched, upserted,
matched, entitites_covered. E um bom historical record mas nao serve para
alertas em tempo real.

---

## 9. Schema Evolution

### Migrations versionadas?

**Sim.** 26 migrations numeradas em `db/migrations/`:
```
001_pncp_raw_bids.sql   → tabela base
002_pncp_supplier_contracts.sql
...
026_contract_intel_truth_v1.sql
```

Padrao de nomenclatura: `{numero}_{descricao}.sql` (alguns com hifen,
ex: `018-td-5.3_esfera_id_check.sql`).

### Schema atual

`db/current-schema.sql` — dump completo do PostgreSQL 16.

### Como adicionar novo campo / nova tabela?

**GAP-18:** Nao ha ferramenta de migration (Alembic, Flyway, etc.). As migrations
sao aplicadas manualmente (ou via script ad-hoc). Nao ha controle de quais
migrations ja foram aplicadas em cada ambiente.

**GAP-19:** Nao ha um processo documentado para:
1. Criar migration → 2. Aplicar em dev → 3. Verificar → 4. Aplicar em prod
As migrations existem como SQL files mas sem orchestration.

---

## 10. Gap Analysis (tabela)

| Pergunta | Resposta | Severidade |
|----------|----------|------------|
| **Adicionar crawler para portal municipal novo** | 2-3 arquivos obrigatorios: (1) modulo crawler com `crawl()`/`transform()`, (2) entrada em `registry.py`. Opcional: migration se schema novo. + test files. | **MEDIO** — o registro centralizado ajuda, mas nao ha checklist ou template claro. |
| **Adicionar campo novo (ex: valor_estimado_editais)** | 3-4 arquivos: (1) migration SQL (ALTER TABLE + RPC), (2) `transformer.py` (mapeamento), (3) adapter se for multipla fontes, (4) possivelmente `pncp_contract.py`. | **MEDIO** — o mapeamento e hardcoded, nao ha metadata-driven schema. |
| **Trocar Selenium por Playwright em todos crawlers** | Alto impacto: ~5 crawlers usam Selenium (dom_sc, doe_sc, sc_compras, transparencia, selenium_crawler_adapter). Cada um tem implementacao diferente. `playwright_fallback.py` existe mas nao e integrado. | **ALTO** — sem adapter layer entre Selenium e Playwright, a troca exige reescrever crawler por crawler. |
| **Circuito de dedup funciona com multiplas fontes?** | **Nao.** Dedup e por ID da fonte (`pncp_id`). Mesmo edital vindo de PCP e PNCP vira 2 registros. | **ALTO** — coverage falso-positivo. |
| **HTTP 200 com corpo vazio?** | `raw_records = crawler.crawl(...)` retorna `[]`. Monitor detecta `fetched=0` → status "empty". Pipeline termina sem upsert. **Nao quebra.** | **BAIXO** — tratado. |
| **Parser encontra layout novo?** | `transform_pncp_item()` usa `.get()` com fallbacks. Campos novos sao ignorados (silenciosamente). Se campo obrigatorio (`numeroControlePNCP`) mudar de nome, `ValueError` e logado e o item e pulado. Nao quebra o batch. | **MEDIO** — degradacao graciosa, mas sem alerta. |
| **Disco enche durante coleta?** | Nao ha handler para `DiskFullError` ou `OSError [ENOSPC]`. A excecao propaga ate `monitor.py` que captura `Exception` genérico, marca como "failed" e continua. O processo pode crashar antes de logar. | **ALTO** — sem protecao explicita. |

---

## 11. Recomendacoes de Refatoracao (minimas, alto impacto)

### R1 — Unificar interface de crawler (GAP-1, GAP-2)

Criar um `BaseCrawlerProtocol` unico que aceite `CrawlRequest` explicitamente:

```python
class CrawlerProtocol(Protocol):
    def crawl(self, request: CrawlRequest) -> FetchResult: ...
    def transform(self, records: list[dict]) -> list[dict]: ...
```

Eliminar o `try/except TypeError` no monitor.py. Todas as fontes existentes
devem ser wrappeadas para conformidade.

### R2 — Raw zone obrigatoria (GAP-3, GAP-4)

Todo crawler DEVE preservar `raw_payload` como JSONB, nao apenas PNCP.
Implementar cold storage opcional (S3/GCS) com retention policy.

### R3 — Cross-source dedup (GAP-8, GAP-9)

Implementar matcher de editais cross-source baseado em:
`digits(orgao_cnpj) + normalize(objeto_compra) + date_range(data_publicacao ± 7d)`.
Usar `generate_content_hash()` de `common.py` como funcao canonica de hash,
eliminando `compute_content_hash()` do transformer.py.

### R4 — Page-level checkpoint (GAP-10)

Substituir checkpoint diario por checkpoint por pagina:
```sql
-- checkpoint_pages: (source, scope, page, last_id, completed)
```
Permite resumir de onde parou. Especialmente importante para PNCP com
`max_pages=200`.

### R5 — Rate limiter por dominio (GAP-12)

Substituir instancia global unica por registry de rate limiters:
```python
_rate_limiters: dict[str, TokenBucketRateLimiter] = {
    "pncp": TokenBucketRateLimiter(rate=10, period=1.0),
    "brasilapi": TokenBucketRateLimiter(rate=3, period=1.0),
    "ibge": TokenBucketRateLimiter(rate=5, period=1.0),
    "default": TokenBucketRateLimiter(rate=1, period=1.0),
}
```

### R6 — Remover stubs perigosos (GAP-7, GAP-11, GAP-16)

Substituir stubs por:
- `ingestion/transformer.py` → raise `NotImplementedError` ou remover
- `ingestion/checkpoint.py` → implementar ou remover
- `metrics.py` / `ingestion/metrics.py` → implementar com `prometheus_client`
  ou logging estruturado real

### R7 — Adapter layer Selenium/Playwright (GAP na tabela sobre Playwright)

Criar `BrowserAdapter` que unifica `selenium.Crawler` e `playwright.async_api`:
```python
class BrowserAdapter:
    async def fetch_page(self, url: str) -> str: ...
    async def screenshot(self, url: str) -> bytes: ...
    async def close(self): ...
```
Selecao do backend por config/env var: `CRAWLER_BROWSER_BACKEND=selenium|playwright`.

### R8 — Lock distribuido contra execucao concorrente (GAP-14)

Usar Redis lock (ou advisory lock PostgreSQL) com TTL para garantir que
apenas uma instancia de cada fonte rode por vez:
```sql
SELECT pg_try_advisory_lock(hash_source) -- PostgreSQL advisory lock
```

### R9 — Monitoramento real (GAP-16, GAP-17)

Implementar `prometheus_client` ou exportar metricas via logging estruturado
para Datadog/CloudWatch. Metricas minimas por fonte:
- `crawler_duration_seconds`
- `crawler_records_total` (labels: source, status)
- `crawler_errors_total` (labels: source, error_type)
- `crawler_last_success_timestamp`

### R10 — Migration tooling (GAP-18, GAP-19)

Adotar `yoyo-migrations` (leve, SQL-only) ou `alembic` para versionamento
de schema com `db migrate` e `db rollback`.

---

**Resumo:** A arquitetura tem pontos fortes (registry centralizado, circuit breakers
por fonte, idempotencia via UPSERT, migrations versionadas) mas sofre de
inconsistencia de interfaces (3 paradigmas), ausencia de dedup cross-source,
stubs perigosos que mascaram funcionalidade faltante, e metricas nao implementadas.
As 10 recomendacoes acima resolvem os gaps mais criticos com impacto
relativamente baixo (R1, R3, R4, R5) e medio (R2, R6, R7, R8, R9, R10).
