# Database Schema — Extra Consultoria

## Overview

- **Tecnologia:** PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1)
- **Database:** `pncp_datalake`
- **Propósito:** DataLake de licitacoes publicas focado em Santa Catarina. Agrega dados de multiplas fontes (PNCP, DOM-SC, PCP, ComprasGov, SC Compras, TCE-SC, Transparencia) com matching de entidades publicas catarinenses e inteligencia de oportunidades.
- **Extensoes instaladas:** `pg_trgm` (text similarity, trigram indexing), `uuid-ossp` (UUID generation)
- **Migration tracks:** 3 tracks identificadas — v1 (archived/diverged), v2 (baseline real), v3 (unified consolidation, pending/partial)
- **Snapshot de referencia:** `supabase/current-schema.sql` — extraido via `pg_dump --schema-only` em 2026-07-11

---

## Migration Tracks

O projeto passou por tres tracks de migracao devido a divergencias historicas entre o schema real e as migrations versionadas:

| Track | Periodo | Arquivos | Status |
|-------|---------|----------|--------|
| **v1** | Original | `db/migrations/001-014.sql` | ARCHIVED — totalmente divergente do schema real |
| **v2** | Baseline | `supabase/migrations/001-v2` a `005-v2` | Baseline do schema real, idempotente |
| **v3** | Consolidacao | `supabase/migrations/006-v3` | Consolidacao de tabelas faltantes (10 novas tabelas) |

### Tabela de tracking

```sql
public._migrations
```

Criada por `_migrations.sql` para rastrear migrations aplicadas. Colunas: `version` (PK), `name`, `applied_at`, `checksum`, `rollback_sql`.

---

## Entity Relationship Diagram (Textual)

```
┌─────────────────────────────────────────┐
│           sc_public_entities            │
│         (entes publicos SC)             │
├─────────────────────────────────────────┤
│ id (PK, INTEGER, SEQUENCE)              │
│ cnpj_8 (TEXT, NOT NULL)                 │
│ razao_social (TEXT, NOT NULL)           │
│ municipio (TEXT)                        │
│ codigo_ibge (TEXT, 7-digit)             │
│ natureza_juridica (TEXT)                │
│ cod_natureza (TEXT)                     │
│ latitude (DOUBLE PRECISION)             │
│ longitude (DOUBLE PRECISION)            │
│ distancia_fk (DOUBLE PRECISION)         │
│ raio_200km (BOOLEAN, DEFAULT false)     │
│ is_active (BOOLEAN, DEFAULT true)       │
│ created_at (TIMESTAMPTZ, DEFAULT now()) │
└──────────────────┬──────────────────────┘
                   │
         ┌─────────┴───────────┐
         │                     │
         ▼                     ▼
┌─────────────────┐  ┌──────────────────────────────────────┐
│ entity_coverage  │  │ pncp_raw_bids                        │
├─────────────────┤  ├──────────────────────────────────────┤
│ entity_id (PK)  │  │ matched_entity_id (FK → id, SET NULL)│
│ source (PK)     │  │ pncp_id (PK, TEXT)                   │
│ last_seen_at    │  │ content_hash (UNIQUE, TEXT)           │
│ total_bids      │  │ orgao_cnpj (TEXT)                    │
│ is_covered      │  │ orgao_razao_social (TEXT)            │
│ within_200km    │  │ objeto_compra (TEXT)                  │
│ match_method*   │  │ tsv (TSVECTOR, auto-trigger)         │
└─────────────────┘  │ source (TEXT, DEFAULT 'pncp')        │
                      │ ingested_at, updated_at (TIMESTAMPTZ)│
                      │ is_active (BOOLEAN, DEFAULT true)    │
                      │ [v3: +11 colunas novas]              │
                      └──────────────────┬───────────────────┘
                                         │
                                         │ content_hash (dedup)
                                         ▼
                              ┌──────────────────────────┐
                              │ pncp_enrichment_cache*   │
                              │ (v3, ON DELETE CASCADE)  │
                              └──────────────────────────┘

┌───────────────────────────────────────┐
│      pncp_supplier_contracts           │
├───────────────────────────────────────┤
│ id (PK, INTEGER, SEQUENCE)            │
│ contrato_id (UNIQUE, TEXT)            │
│ fornecedor_cnpj, fornecedor_nome      │
│ orgao_cnpj, orgao_nome                │
│ objeto_contrato (TEXT)                │
│ valor_total (NUMERIC 18,2)            │
│ data_inicio, data_fim, data_publicacao│
│ uf, municipio                        │
│ source (TEXT, DEFAULT 'pncp')         │
│ ingested_at (TIMESTAMPTZ)             │
│ [v3: +2 colunas]                     │
└───────────────────────────────────────┘

┌─────────────────────────┐  ┌─────────────────────────┐
│   enriched_entities     │  │  coverage_snapshots     │
├─────────────────────────┤  ├─────────────────────────┤
│ cnpj (PK, TEXT)         │  │ id (PK, INTEGER, SEQ)   │
│ razao_social (TEXT)     │  │ snapshot_date (DATE)    │
│ ... (endereco, dados)   │  │ source (TEXT)           │
│ enriched_at (TIMESTAMPTZ)│  │ total/covered_entities  │
│ enriched_source (TEXT)  │  │ pct_covered (NUMERIC)   │
└─────────────────────────┘  └─────────────────────────┘

┌─────────────────────────┐  ┌──────────────────────────┐
│   ingestion_runs        │  │  ingestion_checkpoints    │
├─────────────────────────┤  ├──────────────────────────┤
│ id (PK, INTEGER, SEQ)  │  │ source (PK, TEXT)         │
│ source (TEXT)           │  │ scope_key (PK, TEXT)     │
│ started_at / finished_at│  │ last_page, last_date     │
│ records_fetched/upserted│  │ last_id, records_fetched │
│ status + error_message  │  │ updated_at               │
│ metadata (JSONB)        │  └──────────────────────────┘
└─────────────────────────┘

=== V3 Tables (consolidacao pendente) ===

┌─────────────────────┐    ┌──────────────────────┐
│ entity_hierarchy    │    │ sc_municipalities     │
│ entity_id (PK, FK)  │    │ codigo_ibge (PK)      │
│ parent_entity_id(FK)│    │ municipio (NOT NULL)  │
│ relationship (ENUM) │    │ latitude, longitude   │
│ match_confidence    │    └──────────────────────┘
└─────────────────────┘

┌─────────────────────────┐  ┌──────────────────────────┐
│ coverage_evidence       │  │ opportunity_intel        │
│ (evidence_state enum)   │  │ (core opportunity recs)  │
│ id (BIGSERIAL PK)       │  │ id (BIGSERIAL PK)        │
│ entity_id, source       │  │ content_hash (UNIQUE)    │
│ state (evidence_state)  │  │ 30+ colunas de metadados │
│ run_id, contadores      │  │ ranking, qualidade       │
│ partial unique indexes  │  │ status_canonico (ENUM)   │
└─────────────────────────┘  └──────────────────────────┘

┌─────────────────────┐    ┌───────────────────────────┐
│ engineering_ops     │    │ opportunity_runs           │
│ (derived layer)     │    ├───────────────────────────┤
│ pncp_id (UNIQUE,FK) │    │ id (BIGSERIAL PK)         │
│ classificacao civil │    │ source, scope_key         │
│ geografia SC        │    │ status (ENUM)             │
│ within_200km        │    │ records_new/updated       │
│ content_hash        │    │ metadata (JSONB)          │
└─────────────────────┘    └──────────────────────────┘

┌──────────────────────────┐  ┌─────────────────────────────┐
│ opportunity_coverage     │  │ opportunity_checkpoints      │
│ entity_id, source (PK)  │  │ source, scope_key (PK)       │
│ freshness, count_open   │  │ last_page, last_date, last_id│
│ result (ENUM)           │  │ records_fetched              │
│ FK → sc_public_entities │  └─────────────────────────────┘
└──────────────────────────┘

┌────────────────────────────────┐
│ sc_dados_abertos_backfill_log  │
│ id (SERIAL PK)                 │
│ orgao_cnpj (NOT NULL)          │
│ match_method, motivo           │
│ executed_at (TIMESTAMPTZ)      │
└────────────────────────────────┘
```

---

## Table Inventory

### 1. `public.sc_public_entities`

Cadastro de entes publicos catarinenses.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | INTEGER | PK, SEQUENCE | `nextval(...)` | ID interno auto-incremento |
| `razao_social` | TEXT | NOT NULL | | Razao social do ente publico |
| `cnpj_8` | TEXT | NOT NULL | | CNPJ 8-digit (raiz, sem filiais) |
| `municipio` | TEXT | | | Municipio sede |
| `codigo_ibge` | TEXT | | | Codigo IBGE 7-digit do municipio |
| `natureza_juridica` | TEXT | | | Natureza juridica (ex: MUNICIPIO, AUTARQUIA) |
| `cod_natureza` | TEXT | | | Codigo da natureza juridica |
| `latitude` | DOUBLE PRECISION | | | Latitude da sede |
| `longitude` | DOUBLE PRECISION | | | Longitude da sede |
| `distancia_fk` | DOUBLE PRECISION | | | Distancia de Florianopolis em km |
| `raio_200km` | BOOLEAN | NOT NULL | `FALSE` | TRUE se dentro do raio de 200km de Florianopolis |
| `is_active` | BOOLEAN | NOT NULL | `TRUE` | Soft-delete |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp de criacao |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `sc_public_entities_pkey` | BTREE | `id` | PK |
| `idx_spe_cnpj` | BTREE | `cnpj_8` | Lookup por CNPJ raiz |
| `idx_spe_ibge` | BTREE | `codigo_ibge` | Lookup por codigo IBGE |
| `idx_spe_municipio` | BTREE | `municipio` | Filtro por municipio |
| `idx_spe_natureza` | BTREE | `cod_natureza` | Filtro por natureza juridica |
| `idx_spe_raio` | BTREE | `raio_200km, is_active` | Filtro geografico + ativos |

**Nota:** Nao ha UNIQUE constraint em `cnpj_8`, apenas index BTREE simples. Isso permite duplicatas de CNPJ (nao desejavel).

---

### 2. `public.pncp_raw_bids`

Tabela central de licitacoes/unified bids. Registros de compras publicas de multiplas fontes normalizados em schema unico.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `pncp_id` | TEXT | PK NOT NULL | | Identificador unico (ex: `13714142000162-1-000014/2026`) |
| `objeto_compra` | TEXT | | | Descricao do objeto da licitacao |
| `valor_total_estimado` | NUMERIC(18,2) | | | Valor total estimado |
| `modalidade_id` | INTEGER | | | 1=Leilao, 2=Concurso, 3=Convite, 4=Concorrencia, 5=Pregao, 6=RDC, 7=Dialogo, 8=Inexigibilidade |
| `modalidade_nome` | TEXT | | | Nome descritivo da modalidade |
| `esfera_id` | INTEGER | | | Esfera: 1=Federal, 2=Estadual, 3=Municipal, 4=Distrital |
| `uf` | TEXT | | | UF (ex: SC) |
| `municipio` | TEXT | | | Municipio |
| `codigo_municipio_ibge` | TEXT | | | Codigo IBGE 7-digit |
| `orgao_razao_social` | TEXT | | | Nome do orgao publicador |
| `orgao_cnpj` | TEXT | | | CNPJ do orgao (14 digitos) |
| `data_publicacao` | DATE | | | Data de publicacao |
| `data_abertura` | DATE | | | Data de abertura da sessao |
| `data_encerramento` | DATE | | | Data de encerramento |
| `link_pncp` | TEXT | | | URL oficial PNCP para a licitacao |
| `content_hash` | TEXT | UNIQUE NOT NULL | | SHA256 do payload para dedup |
| `tsv` | TSVECTOR | | | Pre-computed full-text search vector (portugues) |
| `source` | TEXT | NOT NULL | `'pncp'` | Fonte: `pncp`, `dom_sc`, `pcp`, `compras_gov`, `sc_compras` |
| `source_id` | TEXT | | | ID na fonte de origem |
| `matched_entity_id` | INTEGER | FK → sc_public_entities(id) ON DELETE SET NULL | | Ente publico matched |
| `ingested_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp de ingestao |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp de atualizacao |
| `is_active` | BOOLEAN | NOT NULL | `TRUE` | Soft-delete |

**Indexes:**
| Name | Type | Columns | Condition | Notes |
|------|------|---------|-----------|-------|
| `pncp_raw_bids_pkey` | BTREE | `pncp_id` | — | PK |
| `pncp_raw_bids_content_hash_key` | BTREE | `content_hash` | — | UNIQUE dedup |
| `idx_bids_active` | BTREE | `is_active, data_publicacao DESC` | `is_active = true` | Filtro ativos recentes |
| `idx_bids_encerramento` | BTREE | `data_encerramento` | `data_encerramento IS NOT NULL` | Licitacoes encerrando |
| `idx_bids_esfera` | BTREE | `esfera_id` | — | Filtro por esfera |
| `idx_bids_ingested` | BTREE | `ingested_at DESC` | — | Auditoria recente |
| `idx_bids_matched_entity` | BTREE | `matched_entity_id` | `matched_entity_id IS NOT NULL` | Partial: joins coverage |
| `idx_bids_modalidade` | BTREE | `modalidade_id, data_publicacao DESC` | — | Filtro modalidade |
| `idx_bids_orgao_cnpj` | BTREE | `orgao_cnpj` | — | Lookup por orgao |
| `idx_bids_orgao_hash` | BTREE | `orgao_cnpj, content_hash` | — | Dedup por orgao |
| `idx_bids_source` | BTREE | `source` | — | Filtro por fonte |
| `idx_bids_tsv` | GIN | `tsv` | — | Full-text search (portugues) |
| `idx_bids_uf_data` | BTREE | `uf, data_publicacao DESC` | — | Filtro UF + data |
| `idx_bids_uf_source` | BTREE | `uf, source, data_publicacao DESC` | — | Filtro UF + fonte |
| `idx_bids_valor` | BTREE | `valor_total_estimado` | — | Filtro por valor |

**Triggers:**
| Trigger | Event | Function | Description |
|---------|-------|----------|-------------|
| `trg_bids_coverage` | AFTER INSERT | `update_entity_coverage()` | Atualiza `entity_coverage` ao inserir bid |
| `trg_bids_coverage_update` | AFTER UPDATE | `update_entity_coverage_on_update()` | Atualiza `entity_coverage` ao mudar match |
| `trg_bids_updated_at` | BEFORE UPDATE | `set_updated_at()` | Auto-atualiza `updated_at` |

---

### 3. `public.pncp_supplier_contracts`

Contratos de fornecedores vinculados a licitacoes.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | INTEGER | PK, SEQUENCE | `nextval(...)` | ID interno |
| `contrato_id` | TEXT | UNIQUE | | Identificador do contrato na fonte |
| `orgao_cnpj` | TEXT | | | CNPJ do orgao contratante |
| `orgao_nome` | TEXT | | | Nome do orgao contratante |
| `fornecedor_cnpj` | TEXT | | | CNPJ do fornecedor |
| `fornecedor_nome` | TEXT | | | Nome do fornecedor |
| `objeto_contrato` | TEXT | | | Objeto do contrato |
| `valor_total` | NUMERIC(18,2) | | | Valor total do contrato |
| `data_inicio` | DATE | | | Data de inicio da vigencia |
| `data_fim` | DATE | | | Data de fim da vigencia |
| `data_publicacao` | DATE | | | Data de publicacao |
| `uf` | TEXT | | | UF |
| `municipio` | TEXT | | | Municipio |
| `source` | TEXT | NOT NULL | `'pncp'` | Fonte dos dados |
| `source_id` | TEXT | | | ID na fonte de origem |
| `ingested_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp de ingestao |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `pncp_supplier_contracts_pkey` | BTREE | `id` | PK |
| `pncp_supplier_contracts_contrato_id_key` | BTREE | `contrato_id` | UNIQUE (dedup) |
| `idx_psc_data` | BTREE | `data_publicacao DESC` | Ordenacao por data |
| `idx_psc_fornecedor` | BTREE | `fornecedor_cnpj, data_publicacao DESC` | Lookup fornecedor |
| `idx_psc_objeto_trgm` | GIN | `objeto_contrato gin_trgm_ops` | Trigram fuzzy search |
| `idx_psc_orgao` | BTREE | `orgao_cnpj` | Lookup orgao |
| `idx_psc_uf` | BTREE | `uf, data_publicacao DESC` | Filtro UF |
| `idx_psc_valor` | BTREE | `valor_total` | Filtro valor |

---

### 4. `public.enriched_entities`

Cache de enriquecimento de entidades via BrasilAPI/IBGE.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `cnpj` | TEXT | PK NOT NULL | | CNPJ completo (14 digitos) |
| `razao_social` | TEXT | | | Razao social |
| `nome_fantasia` | TEXT | | | Nome fantasia |
| `cnae_principal` | TEXT | | | CNAE principal (7-digit) |
| `cnae_secundarios` | TEXT[] | | | CNAEs secundarios (array) |
| `municipio` | TEXT | | | Municipio |
| `uf` | TEXT | | | UF |
| `codigo_ibge` | TEXT | | | Codigo IBGE 7-digit |
| `natureza_juridica` | TEXT | | | Natureza juridica |
| `logradouro` | TEXT | | | Endereco |
| `bairro` | TEXT | | | Bairro |
| `cep` | TEXT | | | CEP |
| `telefone` | TEXT | | | Telefone |
| `email` | TEXT | | | Email |
| `situacao` | TEXT | | | Situacao cadastral RFB |
| `enriched_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp do enriquecimento |
| `enriched_source` | TEXT | NOT NULL | `'brasilapi'` | Fonte do enriquecimento |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `enriched_entities_pkey` | BTREE | `cnpj` | PK |
| `idx_ee_enriched_at` | BTREE | `enriched_at` | Ordenacao/cleanup TTL |
| `idx_ee_uf` | BTREE | `uf` | Filtro geografico |

---

### 5. `public.entity_coverage`

Controle de cobertura: qual ente publico tem bids recentes de qual fonte.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `entity_id` | INTEGER | PK, FK → sc_public_entities(id) ON DELETE CASCADE NOT NULL | | ID do ente publico |
| `source` | TEXT | PK NOT NULL | | Fonte (pncp, dom_sc, etc.) |
| `last_seen_at` | TIMESTAMPTZ | | | Ultima vez que foi visto |
| `total_bids` | INTEGER | NOT NULL | `0` | Total de bids desta fonte |
| `is_covered` | BOOLEAN | NOT NULL | `FALSE` | TRUE se visto nos ultimos 90 dias |
| `within_200km` | BOOLEAN | NOT NULL | `FALSE` | TRUE se dentro do raio 200km |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `entity_coverage_pkey` | BTREE | `entity_id, source` | PK composta |
| `idx_cov_covered` | BTREE | `is_covered, within_200km` | Cobertura geografica |
| `idx_cov_last_seen` | BTREE | `last_seen_at` | Staleness tracking |
| `idx_cov_source` | BTREE | `source, is_covered` | Cobertura por fonte |

---

### 6. `public.coverage_snapshots`

Snapshots semanais de cobertura para analise de tendencia.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | INTEGER | PK, SEQUENCE | `nextval(...)` | ID interno |
| `snapshot_date` | DATE | NOT NULL | `CURRENT_DATE` | Data do snapshot |
| `source` | TEXT | NOT NULL | | Fonte |
| `total_entities` | INTEGER | NOT NULL | | Total de entes ativos |
| `covered_entities` | INTEGER | NOT NULL | | Entes cobertos |
| `pct_covered` | NUMERIC(5,2) | NOT NULL | | Percentual de cobertura |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp de geracao |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `coverage_snapshots_pkey` | BTREE | `id` | PK |
| `idx_cov_snap_date` | BTREE | `snapshot_date` | Filtro por data |
| `idx_cov_snap_source` | BTREE | `source, snapshot_date` | Serie temporal por fonte |

---

### 7. `public.ingestion_runs`

Audit trail de execucoes de ingestao (crawlers).

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | INTEGER | PK, SEQUENCE | `nextval(...)` | ID interno |
| `source` | TEXT | NOT NULL | | Fonte processada |
| `started_at` | TIMESTAMPTZ | NOT NULL | `now()` | Inicio da execucao |
| `finished_at` | TIMESTAMPTZ | | | Fim da execucao |
| `records_fetched` | INTEGER | NOT NULL | `0` | Registros obtidos |
| `records_upserted` | INTEGER | NOT NULL | `0` | Registros inseridos/atualizados |
| `entities_covered` | INTEGER | NOT NULL | `0` | Entidades cobertas |
| `status` | TEXT | NOT NULL | `'running'` | running / completed / failed |
| `error_message` | TEXT | | | Mensagem de erro |
| `metadata` | JSONB | | | Metadados adicionais |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `ingestion_runs_pkey` | BTREE | `id` | PK |
| `idx_ir_source_status` | BTREE | `source, status` | Runs por fonte |
| `idx_ir_started` | BTREE | `started_at DESC` | Mais recentes primeiro |

---

### 8. `public.ingestion_checkpoints`

Checkpoints de ingestao para crawlers resumeveis.

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `source` | TEXT | PK NOT NULL | `'pncp'` | Fonte |
| `scope_key` | TEXT | PK NOT NULL | | Chave de escopo (ex: `SC-4`) |
| `last_page` | INTEGER | NOT NULL | `0` | Ultima pagina processada |
| `last_date` | DATE | | | Ultima data processada |
| `last_id` | TEXT | | | Ultimo ID processado |
| `records_fetched` | INTEGER | NOT NULL | `0` | Total de registros obtidos |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Timestamp de atualizacao |

**Indexes:**
| Name | Type | Columns | Notes |
|------|------|---------|-------|
| `ingestion_checkpoints_pkey` | BTREE | `source, scope_key` | PK composta |

---

## Views

### V2 baseline (presentes no schema real)

| View | Descricao | Definicao |
|------|-----------|-----------|
| `v_coverage_gaps` | Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes). Ordenado por municipio, razao_social. | `FROM sc_public_entities e WHERE is_active AND NOT EXISTS (SELECT 1 FROM entity_coverage ec WHERE ec.entity_id = e.id AND ec.is_covered)` |
| `v_coverage_gaps_by_municipio` | Agregacao de gaps de cobertura por municipio. Mostra total_entes, entes_descobertos, pct_gap, pct_coberto. | `FROM sc_public_entities e WHERE is_active GROUP BY municipio` |
| `v_coverage_summary` | Resumo de cobertura por fonte + raio_200km + is_covered. Exibe entity_count e pct. | `FROM entity_coverage ec JOIN sc_public_entities e ON e.id = ec.entity_id AND e.is_active` |
| `v_coverage_trend` | Evolucao semanal da cobertura com variacao percentual (LAG). Row number por fonte (rn_desc). | `FROM coverage_snapshots ORDER BY snapshot_date DESC, source` |

### V3 (consolidacao pendente, migration 006)

| View | Descricao |
|------|-----------|
| `v_latest_evidence` | Ultimo estado de evidencia por (entity_id, source, data_type) — DISTINCT ON + ORDER BY completed_at DESC |
| `v_source_health` | Health summary por fonte: total_entity_rows, success_with_data, success_zero, partial, failed states |
| `v_hierarchical_coverage` | Cobertura hierarquica: entidade + parent + cobertura direta vs parent |
| `v_opportunity_open` | Oportunidades abertas/upcoming com dados da entidade (razao_social, municipio, distancia) |
| `v_opportunity_by_source` | Contagem de oportunidades por (source, status_canonico) com ranking GO/REVIEW/NO_GO |
| `v_opportunity_coverage_summary` | Dashboard de cobertura por fonte: entities_attempted, entities_covered, total_records, pct_covered |

---

## Functions & Stored Procedures

### V2 baseline (presentes no schema real)

| Name | Type | Parameters | Description |
|------|------|-----------|-------------|
| `generate_coverage_snapshot` | plpgsql | `snap_date DATE DEFAULT CURRENT_DATE` | Gera snapshot de cobertura para todas as fontes. Chamado por timer semanal. Retorna count de snapshots inseridos. |
| `purge_old_bids` | plpgsql | `p_retention_days INTEGER DEFAULT 400` | Soft-delete (is_active=FALSE) de bids com data_publicacao anterior ao cutoff. Retorna purged_count, remaining_count. |
| `search_datalake` | plpgsql, STABLE | 11 params: `p_ufs TEXT[]`, `p_date_start/end DATE`, `p_tsquery TEXT`, `p_modalidades INT[]`, `p_valor_min/max NUMERIC`, `p_esferas INT[]`, `p_sources TEXT[]`, `p_limit INT DEFAULT 100` | Full-text search multi-filtro. Usa `ts_rank(b.tsv, to_tsquery('portuguese', ...))` + fallback ILIKE. Ordena por rank DESC, data_publicacao DESC. |
| `set_updated_at` | plpgsql, TRIGGER | — | Trigger function: `NEW.updated_at = NOW()` |
| `update_entity_coverage` | plpgsql, TRIGGER | — | AFTER INSERT em pncp_raw_bids: upserts entity_coverage row para o matched_entity_id |
| `update_entity_coverage_on_update` | plpgsql, TRIGGER | — | AFTER UPDATE de matched_entity_id em pncp_raw_bids: upserts entity_coverage |
| `upsert_pncp_raw_bids` | plpgsql | `p_records JSONB` | Batch upsert row-by-row com `ON CONFLICT (content_hash) DO NOTHING`. Gera tsv do objeto_compra. Retorna action (inserted/skipped), pncp_id, content_hash. |
| `upsert_pncp_supplier_contracts` | plpgsql | `p_records JSONB` | Batch upsert row-by-row com `ON CONFLICT (contrato_id) DO NOTHING`. Retorna result (inserted/skipped), id. |

### V3 (consolidacao pendente, migration 006)

| Name | Type | Description |
|------|------|-------------|
| `update_entity_hierarchy_timestamp` | plpgsql, TRIGGER | Auto-atualiza `updated_at` em entity_hierarchy |
| `trg_oi_updated_at_fn` | plpgsql, TRIGGER | Auto-atualiza `updated_at` em opportunity_intel |
| `trg_oi_last_seen_fn` | plpgsql, TRIGGER | Auto-atualiza `last_seen_at` em opportunity_intel |
| `upsert_opportunity_intel` | plpgsql | Batch upsert para opportunity_intel com content_hash dedup. ON CONFLICT DO UPDATE com COALESCE para preservar dados existentes. |

---

## RLS Policy Inventory

**NENHUMA** politica de Row-Level Security configurada em qualquer tabela.

O banco opera como single-user (role `postgres`, superuser). Nao ha RLS porque nao ha multi-tenancy ou separacao de roles de aplicacao. RLS sera necessario se o banco for exposto via Supabase ou API publica no futuro.

---

## Extensions

| Extension | Schema | Description |
|-----------|--------|-------------|
| `pg_trgm` | public | Text similarity measurement e trigram indexing (GIN/GiST operators) |
| `uuid-ossp` | public | UUID generation functions |

---

## Sequences

| Name | Table | Column | Type |
|------|-------|--------|------|
| `sc_public_entities_id_seq` | `sc_public_entities` | `id` | INTEGER (owned) |
| `pncp_supplier_contracts_id_seq` | `pncp_supplier_contracts` | `id` | INTEGER (owned) |
| `coverage_snapshots_id_seq` | `coverage_snapshots` | `id` | INTEGER (owned) |
| `ingestion_runs_id_seq` | `ingestion_runs` | `id` | INTEGER (owned) |

---

## V3 Tables (consolidacao pendente)

A migration `006-v3-unified-schema.sql` adiciona as seguintes tabelas ao schema. Estas tabelas podem ou nao estar presentes no banco real dependendo se a migration foi aplicada.

### 9. `entity_hierarchy`
Mapeamento hierarquico de entidades municipais (entidade filha -> prefeitura parente). Story COVERAGE-1.8.

### 10. `sc_dados_abertos_backfill_log`
Audit log para backfill de municipio em contracts. Story COVERAGE-1.9.

### 11. `sc_municipalities`
Referencia municipal para geolocalizacao do pipeline PNCP.

### 12. `pncp_enrichment_cache`
Cache de enriquecimento de detalhes PNCP (detail_payload, items_payload, documents_payload). FK ON DELETE CASCADE para pncp_raw_bids.

### 13. `engineering_opportunities`
Camada derivada com classificacao de engenharia civil, geografia SC e links PNCP. UNIQUE(pncp_id).

### 14. `coverage_evidence`
Tabela canonica de evidencia de cobertura com enum `evidence_state` (success_with_data, success_zero, partial, connection_failed, auth_failed, parse_failed, transform_failed, persist_failed, not_applicable, not_investigated). Partial unique indexes para rows com/sem entity_id.

### 15. `opportunity_intel`
Core opportunity records: 30+ colunas cobrindo metadata do orgao, dados da licitacao, qualidade, ranking, proveniencia. UNIQUE(content_hash). CHECK constraints para status_canonico, ranking, ranking_confianca, scores.

### 16. `opportunity_checkpoints`
Pagination checkpoints por source/scope_key para crawl de oportunidades.

### 17. `opportunity_runs`
Audit trail de execucao de crawl de oportunidades. CHECK para status (running, completed, completed_zero, failed, partial).

### 18. `opportunity_coverage`
Cobertura por entidade/fonte para fontes de oportunidade. FK para sc_public_entities.

---

## Foreign Key Summary

| FK Name | From | To | Type | On Delete |
|---------|------|----|------|-----------|
| `entity_coverage_entity_id_fkey` | `entity_coverage(entity_id)` | `sc_public_entities(id)` | RESTRICT | CASCADE |
| `fk_bids_matched_entity` | `pncp_raw_bids(matched_entity_id)` | `sc_public_entities(id)` | RESTRICT | SET NULL |
| `pncp_enrichment_cache_pncp_id_fkey` (v3) | `pncp_enrichment_cache(pncp_id)` | `pncp_raw_bids(pncp_id)` | RESTRICT | CASCADE |
| `entity_hierarchy_entity_id_fkey` (v3) | `entity_hierarchy(entity_id)` | `sc_public_entities(id)` | RESTRICT | NO ACTION |
| `entity_hierarchy_parent_entity_id_fkey` (v3) | `entity_hierarchy(parent_entity_id)` | `sc_public_entities(id)` | RESTRICT | NO ACTION |
| `engineering_opportunities_pncp_id_fkey` (v3) | `engineering_opportunities(pncp_id)` | `pncp_raw_bids(pncp_id)` | RESTRICT | CASCADE |
| `fk_oi_run_id` (v3) | `opportunity_intel(run_id)` | `opportunity_runs(id)` | RESTRICT | SET NULL |
| `opportunity_coverage_entity_id_fkey` (v3) | `opportunity_coverage(entity_id)` | `sc_public_entities(id)` | RESTRICT | NO ACTION |

---

## Technical Notes

1. **Naming convention:** Prefixos de indice seguem o padrao `idx_{tabela}_{coluna}` para v2. V3 usa `idx_{abreviacao}_{coluna}` (ex: `idx_ce_state`, `idx_oi_source`).

2. **Soft-delete padrao:** Todas as tabelas principais usam `is_active BOOLEAN DEFAULT TRUE` para soft-delete, exceto `enriched_entities` e tabelas de tracking.

3. **Coverage triggers:** `trg_bids_coverage` e `trg_bids_coverage_update` mantem `entity_coverage` sincronizada automaticamente a cada INSERT/UPDATE em `pncp_raw_bids`.

4. **Full-text search:** `tsv` e populado via funcao `to_tsvector('portuguese', COALESCE(objeto_compra, ''))` durante o upsert, nao via trigger BEFORE INSERT/UPDATE.

5. **Data types:** Datas de publicacao/abertura/encerramento em `pncp_raw_bids` sao DATE (nao TIMESTAMPTZ). `updated_at` e `ingested_at` sao TIMESTAMPTZ.
