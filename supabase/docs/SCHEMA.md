# Database Schema — Extra Consultoria

## Overview

- **Tecnologia:** PostgreSQL 16.14 (Debian)
- **Database:** `postgres` (port 54399)
- **Tamanho:** 4.1 GB
- **Driver:** psycopg2 raw (sem ORM, sem Supabase REST)
- **Propósito:** DataLake de licitacoes publicas focado em Santa Catarina. Agrega dados de multiplas fontes (PNCP, DOM-SC, PCP, ComprasGov, SC Compras, TCE-SC, Transparencia) com matching de entidades publicas catarinenses.
- **Extensoes instaladas:** `pg_trgm` (1.6), `plpgsql` (1.0), `unaccent` (1.1), `vector` (0.8.4)
- **Text Search Dictionary customizado:** `portuguese_smartlic` (parser default + unaccent + portuguese_stem)
- **Single-user:** apenas role `postgres` (superuser); sem RLS, sem roles adicionais

---

## Entity Relationship Diagram (Textual)

```
┌─────────────────────────────┐       ┌──────────────────────────────────┐
│      sc_public_entities     │       │        pncp_raw_bids             │
│  (2.085 entes publicos SC)  │       │  (~199K licitacoes)              │
├─────────────────────────────┤       ├──────────────────────────────────┤
│ id (PK)                     │◄──────│ matched_entity_id (FK)           │
│ cnpj_8 (UNIQUE)             │   FK  │ pncp_id (PK)                     │
│ razao_social                │       │ content_hash (UNIQUE)            │
│ municipio                   │       │ orgao_cnpj                       │
│ codigo_ibge                 │       │ orgao_razao_social               │
│ ...                         │       │ tsv (TSVECTOR, auto-trigger)     │
└─────────────────────────────┘       │ embedding (VECTOR(256))          │
                                      │ ...                              │
        │                              └──────────────────────────────────┘
        │ 1:N (cada ente pode ter              │
        │ varias bids matched)                  │
        │                                       │
        ▼                                       │
┌─────────────────────────────┐                │
│      entity_coverage        │                │
│  (NAO CRIADO no DB real)    │                │
└─────────────────────────────┘                │
                                               │
┌─────────────────────────────┐   ┌──────────────────────────────┐
│  pncp_supplier_contracts    │   │     enriched_entities        │
│  (~3.69M contratos)         │   │  (~13.8K registros)          │
├─────────────────────────────┤   ├──────────────────────────────┤
│ id (PK, BIGSERIAL)          │   │ entity_type (PK)             │
│ numero_controle_pncp        │   │ entity_id (PK)               │
│ ni_fornecedor               │   │ data (JSONB)                 │
│ content_hash (UNIQUE)       │   │ enriched_at                  │
│ uq_psc_fornecedor_contrato  │   └──────────────────────────────┘
│ _ano (UNIQUE)               │
│ ...                         │
└─────────────────────────────┘

┌──────────────────────────────┐  ┌───────────────────────────────┐
│   ingestion_checkpoints      │  │      ingestion_runs           │
│  (0 registros)               │  │  (5 registros)                │
├──────────────────────────────┤  ├───────────────────────────────┤
│ id (PK, GENERATED ALWAYS)    │  │ id (PK, GENERATED ALWAYS)     │
│ source, uf, modalidade_id    │  │ crawl_batch_id (UNIQUE)       │
│ last_date, last_page         │  │ run_type ('full'/'incremental')│
│ status (CHECK constraint)    │  │ status (CHECK constraint)     │
│ crawl_batch_id (UNIQUE comp) │  │ total_fetched, inserted, ...  │
└──────────────────────────────┘  └───────────────────────────────┘
```

---

## Tables

### 1. `public.pncp_raw_bids`

Tabela central de licitacoes/unified bids. ~199K registros, ~665 MB (268 MB dados + 397 MB indices).

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `pncp_id` | TEXT | PK NOT NULL | | Identificador unico PNCP (ex: `13714142000162-1-000014/2026`) |
| `objeto_compra` | TEXT | NOT NULL | | Descricao do objeto da licitacao |
| `valor_total_estimado` | NUMERIC(18,2) | | | Valor estimado |
| `modalidade_id` | INTEGER | NOT NULL | | 4=Concorrencia, 5/6=Pregão, 8=Inexigibilidade |
| `modalidade_nome` | TEXT | | | Nome da modalidade |
| `situacao_compra` | TEXT | | | Situacao (ex: Divulgada, Aberta) |
| `esfera_id` | TEXT | | | Esfera (F=Federal, E=Estadual, M=Municipal, D=Distrital) |
| `uf` | TEXT | NOT NULL | | UF (ex: SC) |
| `municipio` | TEXT | | | Municipio |
| `codigo_municipio_ibge` | TEXT | | | Codigo IBGE 7-digit |
| `orgao_razao_social` | TEXT | | | Nome do orgao publicador |
| `orgao_cnpj` | TEXT | | | CNPJ do orgao (14 digitos) |
| `unidade_nome` | TEXT | | | Nome da unidade compradora |
| `data_publicacao` | TIMESTAMPTZ | | | Data de publicacao |
| `data_abertura` | TIMESTAMPTZ | | | Data de abertura da sessao |
| `data_encerramento` | TIMESTAMPTZ | | | Data de encerramento |
| `link_sistema_origem` | TEXT | | | Link para o sistema de origem |
| `link_pncp` | TEXT | | | Link PNCP oficial |
| `content_hash` | TEXT | UNIQUE NOT NULL | | Hash SHA256 para dedup |
| `source` | TEXT | NOT NULL | `'pncp'` | Fonte dos dados (`pncp`/`dom_sc`/`pcp`/`compras_gov`/`sc_compras`) |
| `crawl_batch_id` | TEXT | | | ID do batch de coleta |
| `is_active` | BOOLEAN | NOT NULL | `TRUE` | Soft-delete flag |
| `tsv` | TSVECTOR | | | Pre-computed full-text search vector |
| `embedding` | VECTOR(256) | | | Embedding vector (OpenAI text-embedding-3-small) |
| `setor_classificado` | TEXT | | | Setor economico classificado |
| `setor_classificado_em` | TIMESTAMPTZ | | | Quando foi classificado |
| `classificacao_metodo` | TEXT | | | Metodo de classificacao |
| `ingested_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Timestamp de ingestao |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Timestamp de atualizacao |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `pncp_raw_bids_pkey` | BTREE | `pncp_id` | PK |
| `idx_pncp_raw_bids_content_hash` | BTREE | `content_hash` | Dedup |
| `idx_pncp_raw_bids_embedding` | HNSW | `embedding vector_cosine_ops` | m=16, ef_construction=64 |
| `idx_pncp_raw_bids_encerramento` | BTREE | `data_encerramento` | WHERE is_active AND data_encerramento IS NOT NULL |
| `idx_pncp_raw_bids_esfera` | BTREE | `esfera_id` | WHERE is_active |
| `idx_pncp_raw_bids_fts` | GIN | `tsv` | Full-text search |
| `idx_pncp_raw_bids_ingested_at` | BTREE | `ingested_at DESC` | |
| `idx_pncp_raw_bids_modalidade` | BTREE | `modalidade_id` | WHERE is_active |
| `idx_pncp_raw_bids_objeto_trgm` | GIST | `objeto_compra gist_trgm_ops` | WHERE is_active (~294 MB) |
| `idx_pncp_raw_bids_uf_date` | BTREE | `uf, data_publicacao DESC` | WHERE is_active |
| `idx_pncp_raw_bids_valor` | BTREE | `valor_total_estimado` | WHERE is_active AND valor_total_estimado IS NOT NULL |

**Triggers:**
- `trg_pncp_raw_bids_tsv` — BEFORE INSERT OR UPDATE OF `objeto_compra` → `pncp_raw_bids_tsv_trigger()` (auto-atualiza `tsv`)
- `trg_pncp_raw_bids_updated_at` — BEFORE UPDATE → `set_updated_at()` (auto-atualiza `updated_at`)

---

### 2. `public.pncp_supplier_contracts`

Tabela de contratos de fornecedores. ~3.69M registros, ~3.43 GB (2.17 GB dados + 1.26 GB indices).

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | BIGINT | PK (sequence) | `nextval(...)` | ID interno |
| `numero_controle_pncp` | TEXT | NOT NULL | | Numero de controle PNCP |
| `ni_fornecedor` | TEXT | NOT NULL | | CNPJ 14d do fornecedor |
| `nome_fornecedor` | TEXT | | | Nome do fornecedor |
| `orgao_cnpj` | TEXT | | | CNPJ do orgao contratante |
| `orgao_nome` | TEXT | | | Nome do orgao contratante |
| `uf` | TEXT | | | UF |
| `municipio` | TEXT | | | Municipio |
| `esfera` | TEXT | | | Esfera |
| `valor_global` | NUMERIC(18,2) | | | Valor global do contrato |
| `data_assinatura` | DATE | | | Data de assinatura |
| `objeto_contrato` | TEXT | | | Objeto do contrato |
| `content_hash` | TEXT | UNIQUE NOT NULL | | Hash SHA256 para dedup |
| `is_active` | BOOLEAN | NOT NULL | `TRUE` | Soft-delete |
| `nr_contrato` | TEXT | | | Numero do contrato |
| `ano` | INTEGER | | | Ano do contrato |
| `data_fim_vigencia` | DATE | | | Fim da vigencia |
| `setor_classificado` | TEXT | | | Setor economico |
| `setor_classificado_em` | TIMESTAMPTZ | | | Quando foi classificado |
| `classificacao_metodo` | TEXT | | | Metodo de classificacao |
| `source` | TEXT | | `'pncp'` | Fonte |
| `ingested_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Indexes (36 total na tabela, varios parciais):**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `pncp_supplier_contracts_pkey` | BTREE | `id` | PK |
| `pncp_supplier_contracts_content_hash_key` | BTREE | `content_hash` | UNIQUE |
| `uq_psc_fornecedor_contrato_ano` | BTREE | `ni_fornecedor, nr_contrato, ano` | UNIQUE (~151 MB) |
| `idx_psc_fornecedor_data` | BTREE | `ni_fornecedor, data_assinatura DESC` | (~171 MB, maior index) |
| `idx_psc_ni_fornecedor` | BTREE | `ni_fornecedor` | (~80 MB) |
| `idx_psc_source_fornecedor` | BTREE | `source, ni_fornecedor` | |
| `idx_psc_data_assinatura` | BTREE | `data_assinatura DESC` | (~65 MB) |
| `idx_psc_active` | BTREE | `is_active` | WHERE is_active = true |

**Triggers:**
- `trg_psc_updated_at` — BEFORE UPDATE → `update_psc_updated_at()`

---

### 3. `public.enriched_entities`

Cache de enriquecimento via BrasilAPI/IBGE. ~13.8K registros, ~6.9 KB.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `entity_type` | TEXT | PK (composite) NOT NULL | | Tipo da entidade (`fornecedor`, `municipio`, `orgao`) |
| `entity_id` | TEXT | PK (composite) NOT NULL | | ID da entidade (CNPJ 14d ou IBGE 7d) |
| `data` | JSONB | NOT NULL | `'{}'` | Payload de enriquecimento |
| `enriched_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Timestamp do enriquecimento |

**Indexes:**
- `enriched_entities_pkey` — BTREE (`entity_type`, `entity_id`)
- `idx_enriched_entities_type_enriched` — BTREE (`entity_type`, `enriched_at DESC`)

---

### 4. `public.ingestion_checkpoints`

Checkpoints de ingestao para crawlers resumeveis. 0 registros (estrutura criada, nunca usada).

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | BIGINT | PK (GENERATED ALWAYS AS IDENTITY) | | |
| `source` | TEXT | NOT NULL | `'pncp'` | Fonte |
| `uf` | TEXT | NOT NULL | | UF alvo |
| `modalidade_id` | INTEGER | NOT NULL | | Modalidade alvo |
| `last_date` | DATE | NOT NULL | | Ultima data processada |
| `last_page` | INTEGER | | `1` | Ultima pagina |
| `records_fetched` | INTEGER | | `0` | Registros obtidos |
| `status` | TEXT | NOT NULL, CHECK(`status` IN ('pending','running','completed','failed')) | `'pending'` | |
| `error_message` | TEXT | | | Mensagem de erro |
| `started_at` | TIMESTAMPTZ | | | |
| `completed_at` | TIMESTAMPTZ | | | |
| `crawl_batch_id` | TEXT | NOT NULL | | ID do batch |

**Indexes:**
- `ingestion_checkpoints_pkey` — BTREE (`id`)
- `uq_ingestion_checkpoints` — UNIQUE BTREE (`source`, `uf`, `modalidade_id`, `crawl_batch_id`)
- `idx_ingestion_checkpoints_batch` — BTREE (`crawl_batch_id`, `status`)
- `idx_ingestion_checkpoints_uf_mod` — BTREE (`uf`, `modalidade_id`)

---

### 5. `public.ingestion_runs`

Audit trail de execucoes de ingestao. 5 registros.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | BIGINT | PK (GENERATED ALWAYS AS IDENTITY) | | |
| `crawl_batch_id` | TEXT | UNIQUE NOT NULL | | ID unico do batch |
| `run_type` | TEXT | NOT NULL, CHECK(`run_type` IN ('full','incremental')) | | Tipo de execucao |
| `status` | TEXT | NOT NULL, CHECK(`status` IN ('running','completed','failed','partial')) | `'running'` | |
| `started_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `completed_at` | TIMESTAMPTZ | | | |
| `total_fetched` | INTEGER | NOT NULL | `0` | |
| `inserted` | INTEGER | NOT NULL | `0` | |
| `updated` | INTEGER | NOT NULL | `0` | |
| `unchanged` | INTEGER | NOT NULL | `0` | |
| `errors` | INTEGER | NOT NULL | `0` | |
| `ufs_completed` | TEXT[] | | | UFs processadas com sucesso |
| `ufs_failed` | TEXT[] | | | UFs com falha |
| `duration_s` | NUMERIC(10,1) | | | Duracao em segundos |
| `metadata` | JSONB | NOT NULL | `'{}'` | Metadados extras |

**Indexes:**
- `ingestion_runs_pkey` — BTREE (`id`)
- `ingestion_runs_crawl_batch_id_key` — UNIQUE BTREE (`crawl_batch_id`)
- `idx_ingestion_runs_started` — BTREE (`started_at DESC`)
- `idx_ingestion_runs_status` — BTREE (`status`) WHERE status IN ('running', 'failed')

---

### 6. `public.sc_public_entities`

Cadastro de 2.085 entes publicos catarinenses (da planilha "Extra - alvos de licitacao. R-0.xlsx").

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | INTEGER | PK (sequence) | `nextval(...)` | |
| `razao_social` | TEXT | NOT NULL | | Razao social do ente |
| `cnpj_8` | TEXT | UNIQUE NOT NULL | | CNPJ 8-digit (raiz) |
| `municipio` | TEXT | | | Municipio sede |
| `codigo_ibge` | TEXT | | | Codigo IBGE 7-digit |
| `natureza_juridica` | TEXT | | | Natureza juridica (ex: MUNICIPIO, AUTARQUIA) |
| `cod_natureza` | TEXT | | | Codigo da natureza juridica |
| `latitude` | DOUBLE PRECISION | | | |
| `longitude` | DOUBLE PRECISION | | | |
| `distancia_fk` | DOUBLE PRECISION | | | Distancia de Florianopolis (km) |
| `raio_200km` | BOOLEAN | NOT NULL | `FALSE` | Dentro do raio de 200km |
| `is_active` | BOOLEAN | NOT NULL | `TRUE` | |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Indexes:**
- `sc_public_entities_pkey` — BTREE (`id`)
- `idx_spe_cnpj_unique` — UNIQUE BTREE (`cnpj_8`)
- `idx_spe_cnpj` — BTREE (`cnpj_8`)
- `idx_spe_municipio` — BTREE (`municipio`)
- `idx_spe_ibge` — BTREE (`codigo_ibge`)
- `idx_spe_natureza` — BTREE (`cod_natureza`)
- `idx_spe_raio` — BTREE (`raio_200km`, `is_active`)

---

## Views

Nenhuma view existe no banco de dados atual.

**Nota:** As migrations 009, 011, e 012 definem as views `v_coverage_summary`, `v_unmatched_bids`, `v_coverage_gaps`, `v_coverage_gaps_by_municipio`, e `v_coverage_trend`, mas estas NAO foram aplicadas ao banco.

---

## Functions & Stored Procedures

### Custom Functions (projeto)

| Name | Type | Parameters | Description |
|------|------|-----------|-------------|
| `search_datalake` | plpgsql, STABLE | `p_ufs TEXT[]`, `p_date_start DATE`, `p_date_end DATE`, `p_tsquery TEXT`, `p_websearch_text TEXT`, `p_modalidades INT[]`, `p_valor_min NUMERIC`, `p_valor_max NUMERIC`, `p_esferas TEXT[]`, `p_modo TEXT`, `p_limit INT`, `p_offset INT`, `p_embedding VECTOR` | Full-text search multi-filtro com suporte a hybrid search (FTS + embedding). Usa `portuguese_smartlic` TSCONFIG. Retorna 15 colunas com `ts_rank`. |
| `search_datalake_trigram_fallback` | SQL, STABLE | `p_query_term TEXT`, `p_ufs TEXT[]`, `p_limit INT` | Fallback trigram similarity via `word_similarity()`. Threshold 0.4. |
| `upsert_pncp_raw_bids` | plpgsql | `p_records JSONB` | Batch upsert com ON CONFLICT (pncp_id) DO UPDATE. Retorna inserted/updated/unchanged. Usa `content_hash` para detectar mudancas. |
| `upsert_pncp_supplier_contracts` | plpgsql | `p_records JSONB` | Batch upsert row-by-row com ON CONFLICT (content_hash). Retorna inserted/updated/unchanged. |
| `upsert_supplier_contracts` | plpgsql, SECURITY DEFINER | `contracts JSONB` | Versao alternativa: `jsonb_to_recordset()` com ON CONFLICT (ni_fornecedor, nr_contrato, ano) DO UPDATE. Retorna SETOF. |
| `purge_old_bids` | plpgsql | `p_retention_days INT DEFAULT 12` | DELETE fisico de bids com `data_publicacao` anterior ao cutoff. |
| `set_updated_at` | plpgsql, TRIGGER | | Trigger function: seta `NEW.updated_at = NOW()` |
| `update_psc_updated_at` | plpgsql, TRIGGER | | Idem para pncp_supplier_contracts |
| `pncp_raw_bids_tsv_trigger` | plpgsql, TRIGGER | | Auto-gera `tsv` de `objeto_compra` com `to_tsvector('portuguese', ...)` |

### Funcoes de extensoes (pgvector, pg_trgm, unaccent)

162 funcoes no total, incluindo pgvector (`vector_cosine_ops`, HNSW/IVFFlat handlers), pg_trgm (`similarity()`, `word_similarity()`, GIN/GiST ops), e unaccent.

---

## Triggers

| Trigger | Table | Event | Function | Description |
|---------|-------|-------|----------|-------------|
| `trg_pncp_raw_bids_tsv` | `pncp_raw_bids` | BEFORE INSERT OR UPDATE OF `objeto_compra` | `pncp_raw_bids_tsv_trigger()` | Auto-popula `tsv` para FTS |
| `trg_pncp_raw_bids_updated_at` | `pncp_raw_bids` | BEFORE UPDATE | `set_updated_at()` | Atualiza `updated_at` |
| `trg_psc_updated_at` | `pncp_supplier_contracts` | BEFORE UPDATE | `update_psc_updated_at()` | Atualiza `updated_at` |

---

## Indexes Summary

36 indexes no total. Maiores destaques:

| Table | Index | Size | Purpose |
|-------|-------|------|---------|
| `pncp_supplier_contracts` | `idx_psc_fornecedor_data` | 171 MB | Lookup fornecedor + data |
| `pncp_supplier_contracts` | `pncp_supplier_contracts_pkey` | 145 MB | PK |
| `pncp_supplier_contracts` | `idx_psc_ni_fornecedor` | 80 MB | Lookup por fornecedor |
| `pncp_supplier_contracts` | `idx_psc_source_fornecedor` | 81 MB | Source + fornecedor |
| `pncp_supplier_contracts` | `idx_psc_data_assinatura` | 65 MB | Ordenacao por data |
| `pncp_supplier_contracts` | `idx_psc_active` | 55 MB | Filtro ativos |
| `pncp_supplier_contracts` | `uq_psc_fornecedor_contrato_ano` | 151 MB | UNIQUE dedup |
| `pncp_raw_bids` | `idx_pncp_raw_bids_objeto_trgm` | 294 MB | Trigram fuzzy search |
| `pncp_raw_bids` | `idx_pncp_raw_bids_fts` | 31 MB | Full-text search GIN |
| `pncp_raw_bids` | `idx_pncp_raw_bids_content_hash` | 25 MB | Dedup |
| `pncp_raw_bids` | `idx_pncp_raw_bids_uf_date` | 10 MB | UF + data |
| `pncp_raw_bids` | `idx_pncp_raw_bids_valor` | 8.9 MB | Filtro valor |

Razao indice/dados: `pncp_raw_bids` = 1.48x (397 MB indices / 268 MB dados), `pncp_supplier_contracts` = 0.58x (1.26 GB / 2.17 GB). A tabela de bids tem mais indices proporcionais porque o `idx_pncp_raw_bids_objeto_trgm` (GIST, 294 MB) consome mais que o dobro dos dados da tabela.

---

## Sequences

| Name | Table | Type |
|------|-------|------|
| `sc_public_entities_id_seq` | `sc_public_entities` | owned by `id` |
| `pncp_supplier_contracts_id_seq` | `pncp_supplier_contracts` | owned by `id` |
| `ingestion_checkpoints_id_seq` | `ingestion_checkpoints` | GENERATED ALWAYS AS IDENTITY |
| `ingestion_runs_id_seq` | `ingestion_runs` | GENERATED ALWAYS AS IDENTITY |

---

## Migration History

| Migration | Applied? | Descricao |
|-----------|----------|-----------|
| `001_pncp_raw_bids.sql` | SIM (evoluido) | Schema original difere do migration — mais colunas, tipos diferentes |
| `002_pncp_supplier_contracts.sql` | SIM (evoluido) | Schema difere significativamente do migration |
| `003_enriched_entities.sql` | SIM (substituido) | Migration define schema `cnpj`+colunas; real usa `entity_type/entity_id`+JSONB |
| `004_ingestion_tables.sql` | SIM (substituido) | Migration define schema diferente do real ambas as tabelas |
| `005_search_datalake_rpc.sql` | SIM (evoluido) | RPC real tem muitos parametros extras (embedding, websearch, offset, trigram) |
| `006_upsert_rpcs.sql` | SIM (evoluido) | RPC real retorna inserted/updated/unchanged, nao action/pncp_id/content_hash |
| `007_sc_public_entities.sql` | SIM (completo) | Match com o migration |
| `008_purge_rpc.sql` | SIM (evoluido) | RPC real faz DELETE fisico em vez de soft-delete |
| `009_indexes_and_coverage.sql` | NAO | Nao aplicada ao banco |
| `010_match_logging.sql` | NAO | Nao aplicada ao banco |
| `011_unmatched_bids_view.sql` | NAO | Nao aplicada ao banco |
| `012_coverage_snapshots.sql` | NAO | Nao aplicada ao banco |

**Observacao critica:** As migrations 001-008 representam uma versao ANTERIOR do schema. O banco real foi evoluido diretamente via scripts Python/DDL avulsos. As migrations 009-012 nunca foram aplicadas.
