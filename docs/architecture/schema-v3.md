# Schema v3 — Unified Schema State

> **Data:** 2026-07-12
> **Propósito:** Documentar a consolidação dos tracks de migração v1 e v2
> **Autor:** Agente de infraestrutura

---

## 1. Resumo Executivo

O repositório possuía **dois tracks de migração divergentes**:

| Track | Diretório | Arquivos | Status |
|-------|-----------|----------|--------|
| **v1** | `db/migrations/` | 001-028 (28 arquivos) | Crescimento orgânico, NUNCA aplicado via runner |
| **v2** | `supabase/migrations/` | _migrations.sql + 001-v2 a 005-v2 (6 arquivos) | Track ATIVO, baseline de produção |
| **v3** | `supabase/migrations/` | 006-v3-unified-schema.sql (1 arquivo) | NOVO — consolida o que faltava |

**Problema resolvido:** O schema de produção correspondia apenas ao baseline 001-v2, sem as tabelas das migrações v1 013-028. O v3 unifica tudo em um único arquivo idempotente.

---

## 2. Migration History

### Linha do Tempo

```
v1 (db/migrations/)  ──────────────────────────────────────────────
  001-012: Schema base (parcialmente coberto pelo v2 001-v2)
  013-028: Otimizações, coverage, contract intel, opportunity intel
           └── NUNCA aplicados em produção ──→  PERDIDOS

v2 (supabase/migrations/)  ────────────────────────────────────────
  001-v2: Baseline extraído de pg_dump --schema-only em 2026-07-11
  002-v2: entity_coverage (adaptado de v1 009)
  003-v2: coverage_views (adaptado de v1 009+011)
  004-v2: coverage_snapshots (adaptado de v1 012)
  005-v2: match_logging (adaptado de v1 010)

v3 (supabase/migrations/)  ──── NOVO ──────────────────────────────
  006-v3: Unifica tudo que estava faltando de v1 013-028
```

### Correspondência v1 → v2/v3

| Migração v1 | Conteúdo | Coberto por |
|-------------|----------|-------------|
| 001-012 | Schema base (tabelas, índices, funções) | v2 001-v2 |
| 013 | GIN index objeto_contrato | v2 001-v2 (já existe em produção) |
| 014 | Fix HNSW search_datalake | v2 001-v2 (função sem embedding) |
| 015 | TTL enriched_entities (constraints) | **v3** (CHECK constraints) |
| 016 | GIN index objeto_compra | v2 001-v2 |
| 017 | Index matched_entity_id | v2 001-v2 |
| 018 | CHECK esfera_id | **v3** |
| 019 | Soft-delete purge_old_bids | v2 001-v2 (função já existe) |
| 020 | Sync local schema (entity_coverage, views) | v2 002-v2, 003-v2, 004-v2 |
| 021 | entity_coverage rebuild + entity_hierarchy | **v3** (entity_hierarchy + colunas) |
| 021_sc | sc_dados_abertos_backfill_log | **v3** |
| 021b | Views e funções coverage | **v3** |
| 022 | match_method em entity_coverage | **v3** |
| 023 | Engineering pipeline (sc_municipalities, pncp_enrichment_cache, engineering_opportunities, colunas pncp_raw_bids) | **v3** |
| 024 | coverage_evidence + evidence_state enum | **v3** |
| 025 | Contract intel views + NULL uniqueness | **v3** (apenas tabelas, views no CLI) |
| 026 | Contract intel truth v1 (views corrigidas) | CLI gerencia |
| 027 | opportunity_intel, opportunity_checkpoints, opportunity_runs, opportunity_coverage | **v3** |
| 028 | opportunity indexes + partial unique indexes | **v3** |

---

## 3. All Tables, Columns, Types, and Constraints

### 3.1 Tabelas do Schema v2 Baseline (001-v2)

Estas tabelas já existem no schema de produção e NÃO são recriadas pelo v3:

#### sc_public_entities

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | INTEGER | PK, DEFAULT nextval('sc_public_entities_id_seq') |
| razao_social | TEXT | NOT NULL |
| cnpj_8 | TEXT | NOT NULL |
| municipio | TEXT | |
| codigo_ibge | TEXT | |
| natureza_juridica | TEXT | |
| cod_natureza | TEXT | |
| latitude | DOUBLE PRECISION | |
| longitude | DOUBLE PRECISION | |
| distancia_fk | DOUBLE PRECISION | |
| raio_200km | BOOLEAN | NOT NULL DEFAULT FALSE |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

**Índices:** idx_spe_cnpj, idx_spe_ibge, idx_spe_municipio, idx_spe_natureza, idx_spe_raio

#### enriched_entities

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| cnpj | TEXT | PK |
| razao_social | TEXT | |
| nome_fantasia | TEXT | |
| cnae_principal | TEXT | |
| cnae_secundarios | TEXT[] | |
| municipio | TEXT | |
| uf | TEXT | |
| codigo_ibge | TEXT | |
| natureza_juridica | TEXT | |
| logradouro | TEXT | |
| bairro | TEXT | |
| cep | TEXT | |
| telefone | TEXT | |
| email | TEXT | |
| situacao | TEXT | |
| enriched_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| enriched_source | TEXT | NOT NULL DEFAULT 'brasilapi' |

**Constraints adicionadas pelo v3:** chk_ee_enriched_at_not_future, chk_ee_cnpj_not_empty, chk_ee_enriched_source_not_empty (NOT VALID)

#### entity_coverage

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| entity_id | INTEGER | PK (com source), FK → sc_public_entities(id) ON DELETE CASCADE |
| source | TEXT | PK |
| last_seen_at | TIMESTAMPTZ | |
| total_bids | INTEGER | NOT NULL DEFAULT 0 |
| is_covered | BOOLEAN | NOT NULL DEFAULT FALSE |
| within_200km | BOOLEAN | NOT NULL DEFAULT FALSE |
| match_method | TEXT | **Adicionado pelo v3** |

**Índices:** idx_cov_covered, idx_cov_last_seen, idx_cov_source, idx_cov_match_method (v3)

#### pncp_raw_bids

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| pncp_id | TEXT | PK |
| objeto_compra | TEXT | |
| valor_total_estimado | NUMERIC(18,2) | |
| modalidade_id | INTEGER | |
| modalidade_nome | TEXT | |
| esfera_id | INTEGER | CHECK (v3): NULL OR IN (1,2,3,4) |
| uf | TEXT | |
| municipio | TEXT | |
| codigo_municipio_ibge | TEXT | |
| orgao_razao_social | TEXT | |
| orgao_cnpj | TEXT | |
| data_publicacao | DATE | |
| data_abertura | DATE | |
| data_encerramento | DATE | |
| link_pncp | TEXT | |
| content_hash | TEXT | UNIQUE |
| tsv | TSVECTOR | |
| source | TEXT | NOT NULL DEFAULT 'pncp' |
| source_id | TEXT | |
| matched_entity_id | INTEGER | FK → sc_public_entities(id) ON DELETE SET NULL |
| ingested_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE |
| situacao_compra | TEXT | **Adicionado pelo v3** |
| unidade_nome | TEXT | **Adicionado pelo v3** |
| link_sistema_origem | TEXT | **Adicionado pelo v3** |
| crawl_batch_id | TEXT | **Adicionado pelo v3** |
| numero_controle_pncp | TEXT | **Adicionado pelo v3** |
| ano_compra | INTEGER | **Adicionado pelo v3** |
| sequencial_compra | INTEGER | **Adicionado pelo v3** |
| informacao_complementar | TEXT | **Adicionado pelo v3** |
| synthetic_id | BOOLEAN | NOT NULL DEFAULT FALSE, **Adicionado pelo v3** |
| synthetic_id_reason | TEXT | **Adicionado pelo v3** |

#### pncp_supplier_contracts

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | INTEGER | PK, DEFAULT nextval('pncp_supplier_contracts_id_seq') |
| contrato_id | TEXT | UNIQUE |
| orgao_cnpj | TEXT | |
| orgao_nome | TEXT | |
| fornecedor_cnpj | TEXT | |
| fornecedor_nome | TEXT | |
| objeto_contrato | TEXT | |
| valor_total | NUMERIC(18,2) | |
| data_inicio | DATE | |
| data_fim | DATE | |
| data_publicacao | DATE | |
| uf | TEXT | |
| municipio | TEXT | |
| source | TEXT | NOT NULL DEFAULT 'pncp' |
| source_id | TEXT | |
| ingested_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| codigo_municipio_ibge | TEXT | **Adicionado pelo v3** |
| municipio_inferido | BOOLEAN | NOT NULL DEFAULT FALSE, **Adicionado pelo v3** |

#### coverage_snapshots, ingestion_checkpoints, ingestion_runs, _migrations

(Tabelas auxiliares cobertas pelo v2 baseline)

### 3.2 Tabelas CRIADAS pelo v3

#### entity_hierarchy

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| entity_id | INTEGER | PK, FK → sc_public_entities(id) |
| parent_entity_id | INTEGER | NOT NULL, FK → sc_public_entities(id) |
| relationship | VARCHAR(32) | NOT NULL, CHECK (prefeitura, camara, autarquia, fundacao, fundo, conselho, outros) |
| match_confidence | VARCHAR(16) | NOT NULL, CHECK (direct, hierarchical, inferred) |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() |
| updated_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() |

**Trigger:** trg_entity_hierarchy_timestamp (BEFORE UPDATE)

#### sc_dados_abertos_backfill_log

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | SERIAL | PK |
| orgao_cnpj | TEXT | NOT NULL |
| match_method | TEXT | |
| municipio | TEXT | |
| codigo_ibge | TEXT | |
| motivo | TEXT | |
| executed_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

#### sc_municipalities

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| codigo_ibge | TEXT | PK |
| municipio | TEXT | NOT NULL |
| latitude | DOUBLE PRECISION | |
| longitude | DOUBLE PRECISION | |
| source | TEXT | NOT NULL DEFAULT 'sc_public_entities_seed' |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

#### pncp_enrichment_cache

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| pncp_id | TEXT | PK, FK → pncp_raw_bids(pncp_id) ON DELETE CASCADE |
| detail_payload | JSONB | |
| items_payload | JSONB | |
| documents_payload | JSONB | |
| fetched_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

#### engineering_opportunities

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | BIGSERIAL | PK |
| pncp_id | TEXT | NOT NULL, UNIQUE, FK → pncp_raw_bids(pncp_id) ON DELETE CASCADE |
| source | TEXT | NOT NULL |
| source_id | TEXT | |
| objeto_compra | TEXT | |
| orgao_cnpj | TEXT | |
| orgao_razao_social | TEXT | |
| codigo_municipio_ibge | TEXT | |
| municipio | TEXT | |
| uf | TEXT | |
| modalidade_id | INTEGER | |
| modalidade_nome | TEXT | |
| valor_total_estimado | NUMERIC(18,2) | |
| data_publicacao | TIMESTAMPTZ | |
| data_abertura | TIMESTAMPTZ | |
| data_encerramento | TIMESTAMPTZ | |
| link_pncp | TEXT | |
| link_sistema_origem | TEXT | |
| is_engineering | BOOLEAN | NOT NULL DEFAULT FALSE |
| engineering_score | INTEGER | NOT NULL DEFAULT 0 |
| engineering_confidence | TEXT | |
| engineering_categories | TEXT[] | NOT NULL DEFAULT '{}' |
| classification_reasons | JSONB | NOT NULL DEFAULT '{}'::jsonb |
| classifier_version | TEXT | |
| exclusion_reason | TEXT | |
| distance_from_florianopolis_km | DOUBLE PRECISION | |
| within_200km | BOOLEAN | NOT NULL DEFAULT FALSE |
| geographic_priority | TEXT | |
| location_confidence | TEXT | |
| first_seen_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| last_seen_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| content_hash | TEXT | |

#### coverage_evidence

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | BIGSERIAL | PK |
| entity_id | INT | (NULL = source-level aggregate) |
| source | TEXT | NOT NULL |
| data_type | TEXT | NOT NULL DEFAULT 'bids' |
| queried_start | DATE | |
| queried_end | DATE | |
| run_id | TEXT | NOT NULL |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| count_obtained | INT | NOT NULL DEFAULT 0 |
| count_transformed | INT | NOT NULL DEFAULT 0 |
| count_persisted | INT | NOT NULL DEFAULT 0 |
| state | evidence_state | NOT NULL DEFAULT 'not_investigated' |
| error_message | TEXT | |
| error_code | TEXT | |
| metadata | JSONB | DEFAULT '{}'::jsonb |

**Partial Unique Indexes:**
- uq_ce_entity_run: UNIQUE (entity_id, source, data_type, run_id) WHERE entity_id IS NOT NULL
- uq_ce_source_aggregate_run: UNIQUE (source, data_type, run_id) WHERE entity_id IS NULL

**CHECK:** ck_success_zero_completeness

**Enum evidence_state:** success_with_data, success_zero, partial, connection_failed, auth_failed, parse_failed, transform_failed, persist_failed, not_applicable, not_investigated

#### opportunity_intel

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | BIGSERIAL | PK |
| source | TEXT | NOT NULL |
| source_id | TEXT | NOT NULL |
| source_url | TEXT | |
| content_hash | TEXT | NOT NULL, UNIQUE (uq_oi_content_hash) |
| numero_controle_pncp | TEXT | |
| crawl_batch_id | TEXT | |
| run_id | BIGINT | FK → opportunity_runs(id) ON DELETE SET NULL |
| ingested_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| first_seen_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| last_seen_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| orgao_cnpj | TEXT | |
| orgao_nome | TEXT | |
| ente_federativo | TEXT | |
| uf | TEXT | NOT NULL |
| municipio | TEXT | |
| codigo_ibge | TEXT | |
| numero_processo | TEXT | |
| numero_edital | TEXT | |
| modalidade | TEXT | |
| modalidade_id | INTEGER | |
| objeto | TEXT | NOT NULL |
| categoria | TEXT | |
| valor_estimado | NUMERIC(18,2) | |
| valor_homologado | NUMERIC(18,2) | |
| valor_semantica | TEXT | |
| data_publicacao | TIMESTAMPTZ | |
| data_abertura | TIMESTAMPTZ | |
| data_encerramento | TIMESTAMPTZ | |
| data_homologacao | TIMESTAMPTZ | |
| status_fonte | TEXT | |
| status_canonico | TEXT | NOT NULL DEFAULT 'unknown', CHECK (open, upcoming, closed, suspended, revoked, annulled, failed, unknown) |
| status_motivo | TEXT | |
| status_data | TIMESTAMPTZ | |
| link_edital | TEXT | |
| link_anexos | TEXT[] | |
| qualidade_score | INTEGER | DEFAULT 0, CHECK (0-100) |
| qualidade_fatores | JSONB | DEFAULT '{}' |
| dados_ausentes | TEXT[] | |
| ranking | TEXT | DEFAULT 'REVIEW', CHECK (GO, REVIEW, NO_GO) |
| ranking_score | INTEGER | DEFAULT 0, CHECK (0-100) |
| ranking_fatores | JSONB | DEFAULT '{}' |
| ranking_regras | TEXT[] | |
| ranking_confianca | TEXT | DEFAULT 'MEDIUM', CHECK (HIGH, MEDIUM, LOW) |
| proveniencia | JSONB | DEFAULT '{}' |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE |
| metadata | JSONB | DEFAULT '{}' |

**Partial Unique Indexes:**
- uq_oi_pncp_id: UNIQUE (numero_controle_pncp) WHERE numero_controle_pncp IS NOT NULL AND is_active = TRUE
- uq_oi_orgao_processo_edital: UNIQUE (orgao_cnpj, numero_processo, numero_edital) WHERE ALL NOT NULL AND is_active = TRUE

**Triggers:** trg_opportunity_intel_updated_at, trg_opportunity_intel_last_seen

#### opportunity_checkpoints

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| source | TEXT | PK |
| scope_key | TEXT | PK |
| last_page | INTEGER | |
| last_date | DATE | |
| last_id | TEXT | |
| records_fetched | INTEGER | DEFAULT 0 |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

#### opportunity_runs

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| id | BIGSERIAL | PK |
| source | TEXT | NOT NULL |
| scope_key | TEXT | |
| started_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| finished_at | TIMESTAMPTZ | |
| records_fetched | INTEGER | DEFAULT 0 |
| records_new | INTEGER | DEFAULT 0 |
| records_updated | INTEGER | DEFAULT 0 |
| pages_processed | INTEGER | DEFAULT 0 |
| pages_expected | INTEGER | |
| status | TEXT | NOT NULL DEFAULT 'running', CHECK (running, completed, completed_zero, failed, partial) |
| error_message | TEXT | |
| metadata | JSONB | DEFAULT '{}' |

#### opportunity_coverage

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| entity_id | INTEGER | PK, FK → sc_public_entities(id) |
| source | TEXT | PK |
| period_start | DATE | |
| period_end | DATE | |
| pages_expected | INTEGER | |
| pages_processed | INTEGER | |
| last_attempt | TIMESTAMPTZ | |
| result | TEXT | CHECK (success, success_zero, partial, error, pending) |
| count_obtained | INTEGER | DEFAULT 0 |
| count_open | INTEGER | DEFAULT 0 |
| freshness | INTERVAL | |
| error_message | TEXT | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

---

## 4. Views Definidas

### Views do Schema v2 (001-v2)

| View | Descrição |
|------|-----------|
| v_coverage_gaps | Entes com gap total de cobertura |
| v_coverage_gaps_by_municipio | Gaps agregados por município |
| v_coverage_summary | Sumário de cobertura por source |
| v_coverage_trend | Evolução semanal da cobertura |
| v_unmatched_bids | Bids sem matched_entity_id |

### Views Criadas pelo v3

| View | Origem | Descrição |
|------|--------|-----------|
| v_latest_evidence | v1 024 | Último estado de evidência por (entity, source, data_type) |
| v_source_health | v1 024 | Saúde por fonte a partir de evidências |
| v_hierarchical_coverage | v1 021 | Cobertura hierárquica (entes herdam da prefeitura) |
| v_opportunity_open | v1 027 | Oportunidades abertas/upcoming com detalhes da entidade |
| v_opportunity_by_source | v1 027 | Sumário de oportunidades por source/status |
| v_opportunity_coverage_summary | v1 027 | Dashboard de cobertura de fontes de oportunidade |

### Views Gerenciadas pelo Contract Intel CLI (026)

| View | Descrição |
|------|-----------|
| v_contract_historical | Contratos históricos (3 anos) no raio 200km |
| v_supplier_winners | Rankings de fornecedores vencedores |
| v_expiring_contracts | Contratos expirando em 90-180 dias |
| v_contract_intel_percentis | Percentis P25/P50/P75 por categoria |

---

## 5. Functions

### Schema v2 Baseline

| Function | Descrição |
|----------|-----------|
| set_updated_at() | Trigger function para updated_at automático |
| upsert_pncp_raw_bids(JSONB) | Insert ou skip por content_hash |
| upsert_pncp_supplier_contracts(JSONB) | Insert ou skip por contrato_id |
| search_datalake(...) | Multi-filter FTS search (assinatura v1, 10 params) |
| update_entity_coverage() | Trigger AFTER INSERT em pncp_raw_bids |
| update_entity_coverage_on_update() | Trigger AFTER UPDATE em pncp_raw_bids |
| generate_coverage_snapshot(DATE) | Gera snapshot semanal de cobertura |
| purge_old_bids(INTEGER) | Soft-delete de bids antigos |

### Schema v3

| Function | Descrição |
|----------|-----------|
| update_entity_hierarchy_timestamp() | Trigger para updated_at em entity_hierarchy |
| trg_oi_updated_at_fn() | Trigger para updated_at em opportunity_intel |
| trg_oi_last_seen_fn() | Trigger para last_seen_at em opportunity_intel |
| upsert_opportunity_intel(JSONB) | Batch upsert para opportunity_intel |

---

## 6. SQLite vs PostgreSQL Differences

O `contract_intel.db` (SQLite) é um backend **secundário/fixture**, nunca a fonte da verdade.

### Diferenças Estruturais

| Aspecto | PostgreSQL | SQLite |
|---------|------------|--------|
| Schema | `public.` schema prefix | Sem schema |
| Tipos | `TIMESTAMPTZ`, `NUMERIC(18,2)`, `JSONB` | `TEXT`, `REAL`, sem JSONB nativo |
| View | `CREATE OR REPLACE VIEW` | Não suporta views (usa queries inline) |
| Full-text | `TSVECTOR`, GIN indexes, `ts_rank()` | Não suporta (ILIKE básico) |
| Enums | `CREATE TYPE evidence_state AS ENUM (...)` | CHECK constraints |
| Array | `TEXT[]`, `INTEGER[]` | Não suporta |
| Triggers | Suporte completo | Limitado |
| Concorrência | Multi-usuário, MVCC | Single-writer |
| Unique NULL behavior | Partial unique indexes | NULL = unique in SQLite |

### Tabelas SQLite no contract_intel.db

| Tabela | Equivalente PostgreSQL | Diferenças |
|--------|----------------------|------------|
| target_universe | sc_public_entities (filtrada) | Apenas entes raio_200km; colunas simplificadas (distancia_km, without_200km) |
| pncp_supplier_contracts | pncp_supplier_contracts | Usa nomes reais de coluna (numero_controle_pncp, ni_fornecedor, etc.) |

### Limitações do SQLite para Manifesto de Readiness

O `cli.py manifesto` retorna `uncertainty: True` para todas as capacidades quando usa SQLite, porque:
1. Não tem as views analíticas do PostgreSQL
2. Não tem TSVECTOR para full-text search
3. Não tem PERCENTILE_CONT para percentis
4. Não tem suporte a arrays (GROUP_CONCAT é limitado)

---

## 7. Path to Supabase Self-Hosted

Para migrar do PostgreSQL local para Supabase self-hosted:

### O que mudaria

1. **Conexão:** Substituir `LOCAL_DATALAKE_DSN` por `SUPABASE_DATABASE_URL` no `.env`
2. **Extensions:** `pg_trgm` e `uuid-ossp` são padrão no Supabase; `pgvector` precisaria ser habilitado
3. **Sequences:** As sequences (sc_public_entities_id_seq, etc.) funcionam igual
4. **Migrations:** O sistema de tracking `_migrations` funciona igual — aplicar via `psql` com Supabase DSN
5. **RLS:** Supabase adiciona Row Level Security — as tabelas existentes precisariam de políticas RLS
6. **Edge Functions:** Em vez de cron local, usar Supabase Edge Functions + pg_cron

### Arquivos que precisariam de adaptação

| Arquivo | O que mudar |
|---------|-------------|
| scripts/apply-migrations.sh | Usar `$SUPABASE_DATABASE_URL` em vez de `$LOCAL_DATALAKE_DSN` |
| scripts/contract_intel/cli.py | A `_get_connection()` já suporta DSN — só precisa da env var |
| supabase/migrations/*.sql | Adicionar `CREATE POLICY` para RLS se necessário |
| Scripts de crawl | Verificar se usam `search_path` corretamente |

### Passos para migração

1. `pg_dump` do PostgreSQL local → arquivo `.sql`
2. Aplicar dump no Supabase via `psql $SUPABASE_DATABASE_URL -f dump.sql`
3. Verificar extensions: `CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;`
4. Aplicar v3: `bash scripts/apply-migrations.sh --dsn "$SUPABASE_DATABASE_URL"`
5. Testar: `bash scripts/verify-schema-divergence.sh --dsn "$SUPABASE_DATABASE_URL"`

---

## 8. Schema Divergence Report

### Antes do v3

- **Tabelas faltando:** 10 (entity_hierarchy, sc_dados_abertos_backfill_log, sc_municipalities, pncp_enrichment_cache, engineering_opportunities, coverage_evidence, opportunity_intel, opportunity_checkpoints, opportunity_runs, opportunity_coverage)
- **Colunas faltando em tabelas existentes:** ~15 (match_method, situacao_compra, numero_controle_pncp, etc.)
- **Enums faltando:** 1 (evidence_state)
- **Views faltando:** 6

### Depois do v3

- **Tabelas:** Todas as 10 tabelas criadas (IF NOT EXISTS)
- **Colunas:** Todas adicionadas via ALTER TABLE ADD COLUMN IF NOT EXISTS
- **Constraints:** Todas adicionadas (CHECK, UNIQUE, FK)
- **Enums:** evidence_state criado
- **Views:** v_latest_evidence, v_source_health, v_hierarchical_coverage, v_opportunity_open, v_opportunity_by_source, v_opportunity_coverage_summary
- **Functions:** upsert_opportunity_intel, trigger functions
- **Índices:** ~40 índices (B-tree, GIN, partial unique)

### Divergências Remanescentes (conhecidas)

1. **pncp_supplier_contracts column names:** O v2 baseline usa `contrato_id`, `fornecedor_cnpj`, `fornecedor_nome`, `valor_total`, `data_inicio`, `data_fim` enquanto alguns scripts esperam `numero_controle_pncp`, `ni_fornecedor`, `nome_fornecedor`, `valor_global`, `data_assinatura`, `data_fim_vigencia`. **Nota:** produção atualmente reflete o v2 baseline — os nomes alternativos são expectativas do código que ainda não foram aplicadas.
2. **Contract Intel views (026):** As views `v_contract_historical`, `v_supplier_winners`, `v_expiring_contracts` são gerenciadas pelo CLI (aplicadas via `_ensure_views_pg()`), não pelo sistema de migrations.

---

## 9. Rollback Procedure

Reverter o v3 se necessário:

```sql
-- Listar o que foi aplicado
SELECT version, name, applied_at FROM public._migrations WHERE version = '006-v3';

-- Tabelas para DROP (ordem respeitando FKs):
DROP TABLE IF EXISTS public.opportunity_coverage CASCADE;
DROP TABLE IF EXISTS public.opportunity_runs CASCADE;
DROP TABLE IF EXISTS public.opportunity_checkpoints CASCADE;
DROP TABLE IF EXISTS public.opportunity_intel CASCADE;
DROP TABLE IF EXISTS public.coverage_evidence CASCADE;
DROP TYPE IF EXISTS evidence_state;
DROP TABLE IF EXISTS public.engineering_opportunities CASCADE;
DROP TABLE IF EXISTS public.pncp_enrichment_cache CASCADE;
DROP TABLE IF EXISTS public.sc_municipalities CASCADE;
DROP TABLE IF EXISTS public.sc_dados_abertos_backfill_log CASCADE;
DROP TABLE IF EXISTS public.entity_hierarchy CASCADE;

-- Views para DROP
DROP VIEW IF EXISTS public.v_opportunity_coverage_summary CASCADE;
DROP VIEW IF EXISTS public.v_opportunity_by_source CASCADE;
DROP VIEW IF EXISTS public.v_opportunity_open CASCADE;
DROP VIEW IF EXISTS public.v_hierarchical_coverage CASCADE;
DROP VIEW IF EXISTS public.v_source_health CASCADE;
DROP VIEW IF EXISTS public.v_latest_evidence CASCADE;

-- Funções para DROP
DROP FUNCTION IF EXISTS public.upsert_opportunity_intel;
DROP FUNCTION IF EXISTS public.trg_oi_last_seen_fn;
DROP FUNCTION IF EXISTS public.trg_oi_updated_at_fn;
DROP FUNCTION IF EXISTS public.update_entity_hierarchy_timestamp;

-- Remover colunas adicionadas (opcional — dados seriam perdidos)
ALTER TABLE public.entity_coverage DROP COLUMN IF EXISTS match_method;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS situacao_compra;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS unidade_nome;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS link_sistema_origem;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS crawl_batch_id;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS numero_controle_pncp;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS ano_compra;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS sequencial_compra;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS informacao_complementar;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS synthetic_id CASCADE;
ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS synthetic_id_reason;
ALTER TABLE public.pncp_supplier_contracts DROP COLUMN IF EXISTS codigo_municipio_ibge;
ALTER TABLE public.pncp_supplier_contracts DROP COLUMN IF EXISTS municipio_inferido;

-- Remover tracking
DELETE FROM public._migrations WHERE version = '006-v3';
```

---

*Documento gerado em 2026-07-12 como parte da unified schema v3 consolidation.*
