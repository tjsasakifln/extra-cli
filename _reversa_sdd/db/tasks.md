# Tasks — Módulo `db`

> 🟢 CONFIRMADO

### T1: Schema Core
- **Arquivo legado:** `db/migrations/001_pncp_raw_bids.sql`
- **Confiança:** 🟢
- **Descrição:** Criar tabela `pncp_raw_bids` com 25 colunas, FTS PT-BR (TSVECTOR + GIN), 12 índices B-tree, trigger `set_updated_at()`. Extensões: `pg_trgm`, `uuid-ossp`.
- **Critério de pronto:** Tabela criada. FTS funcional. Índices operantes.

### T2: RPCs
- **Arquivo legado:** `db/migrations/005_search_datalake_rpc.sql`, `006_upsert_rpcs.sql`, `008_purge_rpc.sql`
- **Confiança:** 🟢
- **Descrição:** `upsert_pncp_raw_bids(jsonb)` com ON CONFLICT. `search_datalake()` com FTS. `purge_old_records()`.
- **Critério de pronto:** 3 RPCs funcionais. Batch upsert correto. FTS retorna resultados.

### T3: Seed Entities
- **Arquivo legado:** `db/seed/001_sc_entities.py`
- **Confiança:** 🟢
- **Descrição:** Parse Excel "Extra - alvos de licitação. R-0.xlsx". Extrair razão social, CNPJ base, município, código IBGE, natureza jurídica, raio_200km. INSERT 2.085 registros.
- **Critério de pronto:** 2.085 entidades inseridas. CNPJ 8 dígitos. Raio 200km classificado.

### T4: Coverage Tracking
- **Arquivo legado:** `db/migrations/009_indexes_and_coverage.sql`, `012_coverage_snapshots.sql`
- **Confiança:** 🟢
- **Descrição:** Tabela `entity_coverage` com trigger pós-upsert. `coverage_snapshots` com job diário.
- **Critério de pronto:** Coverage atualizado automaticamente. Snapshots históricos.
