# Database — Design

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

## Schema (8 tabelas, PostgreSQL 18.4)

```
sc_public_entities (2.085) ──< pncp_raw_bids (~199K) ──< entity_coverage
enriched_entities (~13.8K)     pncp_supplier_contracts (~3.69M)
coverage_snapshots             ingestion_checkpoints
ingestion_runs (5)
```

**Extensões:** pg_trgm, uuid-ossp, unaccent, vector

## Funções PL/pgSQL (10)

| Função | Args | Retorno | Propósito |
|--------|------|---------|-----------|
| `search_datalake` | 10 params | TABLE(13 cols) | FTS multi-filtro + ILIKE |
| `upsert_pncp_raw_bids` | p_records JSONB | TABLE | Batch upsert: ON CONFLICT content_hash DO NOTHING |
| `upsert_pncp_supplier_contracts` | p_records JSONB | TABLE | Batch upsert: ON CONFLICT contrato_id DO NOTHING |
| `purge_old_bids` | p_retention_days INT | TABLE | Soft-delete (is_active=FALSE) |
| `purge_old_bids_hard` | p_soft_retention_days INT | — | Hard-delete pós soft-retention |
| `ttl_cleanup_enriched_entities` | p_ttl_days INT | — | DELETE expired cache |
| `set_updated_at` | — | TRIGGER | BEFORE UPDATE auto timestamp |
| `update_entity_coverage` | — | TRIGGER | AFTER INSERT: upsert entity_coverage |
| `update_entity_coverage_on_update` | — | TRIGGER | AFTER UPDATE: update entity_coverage |
| `generate_coverage_snapshot` | snap_date DATE | — | INSERT coverage_snapshots por source |

## Views (5)
`v_coverage_summary`, `v_coverage_gaps`, `v_coverage_gaps_by_municipio`, `v_coverage_trend`, `v_unmatched_bids`

## Índices (33)
Destaques: GIN `tsv` (FTS), GIN `objeto_compra gin_trgm_ops`, HNSW `embedding` (pgvector), UNIQUE `content_hash`, UNIQUE `cnpj_8`

## Divergências Schema Real vs Migrations v1
🔴 `esfera_id` TEXT vs INT, `data_*` TIMESTAMPTZ vs DATE, `enriched_entities` JSONB vs plano, 0 views no real, `vector` ausente nas v1

**Resolução:** Baseline v2 (`001-v2_initial_schema.sql`, 840 linhas, pg_dump --schema-only)

🟢 CONFIRMADO — Schema dump real + DB-AUDIT.md + migration-rebuild.md
