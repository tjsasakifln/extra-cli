# Migracoes Antigas (db/migrations/) — ARCHIVED

Este diretorio contem as **migrations v1 (001-014)** que foram substituidas pela
baseline v2 como parte da resolucao do debito TD-DB-01 (CRITICAL).

## Por que foram substituidas?

As 14 migrations em `db/migrations/` divergiram do schema real do banco a
ponto de ser impossivel recriar o banco a partir delas. As causas principais:

1. **Alteracoes manuais no schema** — DDL executado diretamente no banco sem
   migration correspondente
2. **Migrations com escopo incremental** — 014 arquivos que deveriam ser
   aplicados sequencialmente, mas muitos na refletem o estado atual
3. **Ausencia de tracking** — Nao havia tabela `_migrations` para registrar
   quais migrations foram aplicadas

## O que foi feito

As migrations v2 estao em `supabase/migrations/`:

| Migration | Descricao |
|-----------|-----------|
| `_migrations.sql` | Tabela de tracking de migrations (TD-DB-17) |
| `001-v2_initial_schema.sql` | Baseline completa do schema real |

## Migrations v1 — Inventario

| # | Arquivo | Status | Observacao |
|---|---------|--------|------------|
| 001 | `001_pncp_raw_bids.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 002 | `002_pncp_supplier_contracts.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 003 | `003_enriched_entities.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 004 | `004_ingestion_tables.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 005 | `005_search_datalake_rpc.sql` | SUBSTITUIDA | Funcao search_datalake na v2 mantem assinatura original (10 params) |
| 006 | `006_upsert_rpcs.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 007 | `007_sc_public_entities.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 008 | `008_purge_rpc.sql` | SUBSTITUIDA | Incorporada na v2 baseline |
| 009 | `009_indexes_and_coverage.sql` | SUBSTITUIDA | Adaptada como `002-v2-td-2.2_entity_coverage.sql` (TD-2.2) |
| 010 | `010_match_logging.sql` | SUBSTITUIDA | Adaptada como `005-v2-td-2.2_match_logging.sql` (TD-2.2) |
| 011 | `011_unmatched_bids_view.sql` | SUBSTITUIDA | Adaptada como `003-v2-td-2.2_coverage_views.sql` (TD-2.2) |
| 012 | `012_coverage_snapshots.sql` | SUBSTITUIDA | Adaptada como `004-v2-td-2.2_coverage_snapshots.sql` (TD-2.2) |
| 013 | `013_td-1.1_gin_index_objeto_contrato.sql` | DIVERGENTE | GIN index em objeto_contrato existe, mas sem `embedding` no schema real |
| 014 | `014_td-1.1_fix_hnsw_expression.sql` | DIVERGENTE | search_datalake com 13 params + pgvector NAO existe no schema real |

## Divergencias conhecidas (migrations v1 vs schema real)

Ver `docs/td-001/migration-rebuild.md` para analise detalhada de cada
divergencia entre as migrations v1 e o schema real do banco.

## Nota sobre setup_db.sh

O script `db/setup_db.sh` continua aplicando as migrations em
`db/migrations/` para compatibilidade com ambientes existentes. Para setups
novos, use o diretorio `supabase/migrations/` com as migrations v2.

## Rollback

Caso seja necessario reverter para as migrations v1:
1. Backup completo do banco (ver `scripts/backup-database.sh`)
2. Aplicar `db/setup_db.sh` no ambiente de destino
3. Validar que o schema corresponde ao esperado
4. Atualizar esta documentacao
