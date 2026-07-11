# Resume/Checkpoints para Crawlers

**Referencia:** TD-DB-10 (MEDIUM)
**Story:** TD-5.2
**Data da decisao:** 2026-07-11
**Autor:** @dev (Dex)

---

## 1. Decisao Principal

**IMPLEMENTAR** sistema de resume/checkpoints para crawlers.

Os crawlers sao **batch-based** (operam por janela de datas com paginacao multi-pagina), nao per-orgao individual. Portanto, checkpoints sao essenciais para evitar perda de progresso em caso de falha no meio de um ciclo de crawl.

## 2. Analise Tecnica

### Arquitetura dos Crawlers

Cada crawler implementa a interface:

```python
def crawl(mode: str = "full") -> list[dict]:    # busca dados brutos da API
def transform(records: list[dict]) -> list[dict]: # normaliza para schema unificado
```

O `orchestrator.crawl_source()` executa o pipeline completo:

1. **Crawl** — `crawler.crawl(mode)` acumula registros em memoria via paginacao
2. **Transform** — normaliza para schema `pncp_raw_bids`
3. **Upsert** — insere/atualiza via RPC do banco
4. **Entity Match** — associa licitacoes com entidades (exceto contracts)

Se uma falha ocorre na paginacao da Fase 1, **todo o progresso e perdido**.

### Por que nao crawlers per-orgao?

A analise mostra que:

- **PNCP:** Crawleia por (UF, modalidade, dia) — 3 modalidades x 1 UF x N dias
- **DOM-SC:** Crawleia por categorias (6, 7, 28) em janela de datas — nao por orgao
- **PCP:** Crawleia por janela de datas, filtra UF client-side
- **ComprasGov:** Crawleia por janela de datas via 2 endpoints
- **Transparencia:** Crawleia por portal municipal sequencialmente
- **TCE-SC:** Crawleia por janela de datas

Nenhum crawler opera por orgao individual — todos sao batch-based.

### Tabela `ingestion_checkpoints`

A tabela ja existe (migration 004) com schema:

```sql
CREATE TABLE ingestion_checkpoints (
    source          TEXT NOT NULL DEFAULT 'pncp',
    scope_key       TEXT NOT NULL,           -- uf, municipio, modalidade, ou "default"
    last_page       INT NOT NULL DEFAULT 0,
    last_date       DATE,
    last_id         TEXT,                    -- ultimo record ID (source-specific)
    records_fetched INT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, scope_key)
);
```

Ja possui 0 registros porque nenhum crawler integrava checkpoints ate esta story.

### Codigo Pre-existente

Havia um modulo `scripts/crawl/checkpoint.py` herdado do package `ingestion/` (deprecado)
que usava um schema diferente (`uf`, `modalidade_id`, `crawl_batch_id`, `status`, `error_message`),
incompativel com a migration 004. Este modulo foi reescrito para usar o schema real.

## 3. Modelo de Checkpoint

### Nivel: Source-level

Cada source (pncp, dom_sc, doe_sc, etc.) salva **um checkpoint** apos conclusao
bem-sucedida. O escopo padrao e `"default"`.

| Aspecto | Decisao |
|---------|---------|
| Granularidade | Source-level (nao page-level) |
| Quando salvar | Apos `crawl_source()` completar todas as 4 fases |
| Quando verificar | Modo `incremental` — se checkpoint de hoje existe, pula |
| Tabela | `ingestion_checkpoints` (migration 004) |
| Chave | `(source, scope_key)` — source + "default" |
| Driver | `psycopg2` (consistente com o orchestrator) |

### Arquivo: `scripts/crawl/checkpoint.py`

O modulo expoe **duas APIs** coexistindo no mesmo arquivo:

#### API Sync (psycopg2) — usada pelo orchestrator.py

Funcoes que operam na tabela `ingestion_checkpoints` com PK `(source, scope_key)`:

| Funcao | Descricao |
|--------|-----------|
| `is_crawl_completed_today(conn, source, scope_key="default")` | True se checkpoint de hoje existe |
| `get_checkpoint(conn, source, scope_key="default")` | Retorna checkpoint row ou None |
| `save_checkpoint(conn, source, scope_key="default", last_date=None, records_fetched=0)` | Upsert checkpoint |
| `delete_checkpoint(conn, source, scope_key="default")` | Remove checkpoint (reset manual) |

#### API Async (Supabase) — usada pelo bids_crawler.py (legado)

Funcoes que operam na tabela `ingestion_checkpoints` com PK `(uf, modalidade_id, crawl_batch_id)` usando o cliente Supabase assincrono:

| Funcao | Descricao |
|--------|-----------|
| `get_last_checkpoint(uf, modalidade, source="pncp")` | Retorna last_date ou None |
| `save_checkpoint(uf, modalidade, last_date, records_fetched, crawl_batch_id, source="pncp")` | Upsert checkpoint |
| `mark_checkpoint_failed(uf, modalidade, crawl_batch_id, error_message, source="pncp")` | Marca checkpoint como failed |
| `create_ingestion_run(crawl_batch_id, run_type)` | Cria registro de run |
| `complete_ingestion_run(crawl_batch_id, ...)` | Finaliza run com estatisticas |

### Driver e Consistencia

O `orchestrator.py` usa **psycopg2** (sincrono) para todas as operacoes de banco,
incluindo checkpoints. O `bids_crawler.py` legado usa **Supabase** (assincrono).
Ambos os conjuntos de funcoes convivem em `checkpoint.py` sem conflito --
os nomes sao distintos e os modulos importam apenas o que precisam.

### Integracao no Orchestrator (`scripts/crawl/orchestrator.py`)

```
crawl_source(source, entities, mode):
  if mode == "incremental" AND is_crawl_completed_today(conn, source):
      return SKIPPED  # ja completou hoje
  ...
  # Pipeline normal
  save_checkpoint(conn, source, last_date=today, records_fetched=N)
  return OK
```

### Fluxo de Resume

```
monitor.py --source all --mode incremental
  └─ orchestrator.crawl_source("pncp", entities, "incremental")
       ├─ Checkpoint existe para hoje? SIM → SKIP
       └─ Checkpoint existe para hoje? NAO → crawl completo
            ├─ Crawl → Transform → Upsert → Match
            └─ save_checkpoint(pncp, "default", last_date=2026-07-11, records=142)
  └─ orchestrator.crawl_source("dom_sc", entities, "incremental")
       ├─ Checkpoint existe para hoje? SIM → SKIP
       └─ ...
```

## 4. Decisoes de Design

| Opcao | Escolhida | Alternativa Rejeitada | Razao |
|-------|-----------|----------------------|-------|
| Granularidade | Source-level | Page-level | Page-level exigiria modificar cada crawler (OUT de escopo) |
| Driver (sync) | psycopg2 | supabase | Orchestrator usa psycopg2; consistencia evita dupla conexao |
| Driver (async) | Supabase | — | Mantido para compatibilidade com bids_crawler.py legado |
| Tabela | Migration 004 | Nova tabela | Reutilizar schema existente evita mais migrations |
| ON CONFLICT | PK upsert | INSERT + UPDATE | Upsert e mais seguro e atomico |
| Scope padrao | "default" | source nome | Permite expandir para sub-scopos (por UF, modalidade) no futuro |

## 5. Proximos Passos (Futuro — Fora de Escopo)

- **Page-level checkpoints:** Modificar crawlers individuais para salvar checkpoint
  a cada pagina, permitindo resume intra-crawl (nao apenas source-level).
- **Sub-scopos:** Usar `scope_key` para granularidade por UF ou modalidade,
  permitindo resume parcial de fontes com multiplas combinacoes (ex: PNCP).
- **Stale checkpoint cleanup:** Job periodico para limpar checkpoints antigos
  (ex: > 30 dias) e evitar acumulo.

## 6. Rollback

Caso seja necessario reverter:

1. Remover chamadas a `save_checkpoint()` e `is_crawl_completed_today()` em
   `orchestrator.py`
2. Remover funcoes sync (`is_crawl_completed_today`, `save_checkpoint`,
   `get_checkpoint`, `delete_checkpoint`) de `checkpoint.py` — manter apenas
   funcoes async legadas do `bids_crawler.py`
3. Reverter documentacao para refletir apenas API async Supabase
4. A tabela `ingestion_checkpoints` permanece — dados de checkpoint ocupam
   espaco negligible (~1KB por source)

## 7. Referencias

- Migration 004: `db/migrations/004_ingestion_tables.sql`
- Modulo de checkpoint: `scripts/crawl/checkpoint.py`
- Orchestrator: `scripts/crawl/orchestrator.py`
- Story: `docs/stories/epics/epic-td-001-resolution/story-TD-5.2-resume-crawlers.md`
- Technical Debt Assessment: `docs/prd/technical-debt-assessment.md` (TD-DB-10)
