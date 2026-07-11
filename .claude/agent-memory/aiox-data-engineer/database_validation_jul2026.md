---
name: database-validation-2026-07-11
description: Schema and data quality baseline for PostgreSQL datalake (4.1GB, 6 tables) as of 2026-07-11
metadata:
  type: project
---

# Database State (2026-07-11)

Database: `postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres` (4.1 GB)

## Tables

| Table | Rows | Size | Notes |
|-------|------|------|-------|
| `pncp_supplier_contracts` | 3,689,859 | 3.4 GB | 50.6K anomalous dates (1.4%), incl. year 8406 |
| `pncp_raw_bids` | 199,378 | 665 MB | Last bid 2026-06-29 (12d stale), 81% classified |
| `enriched_entities` | 13,842 | 6.9 MB | JSONB-only, no direct join column |
| `sc_public_entities` | 2,085 | 1.5 MB | SC orgaps with geo + cnpj_8 |
| `ingestion_runs` | 5 | 80 kB | 3 stuck in 'running' since 2026-07-02 |
| `ingestion_checkpoints` | 0 | 40 kB | **Empty** -- checkpointing not working |

## Critical Issues

- **3 stuck ingestion runs** (IDS 3,4,5) in 'running' status since 2026-07-02 (8.7 days). Probably crashed mid-crawl.
- **ingestion_checkpoints empty** -- crawler has no resume state.
- **Missing 8 expected tables** (search_results_cache, profiles, alerts, pipeline_items, leads, organizations, digital_products, classification_feedback)

## Medium Issues

- 50,638 contracts outside 2020-2026 date range (includes 8406-05-16 and 2102-09-24)
- enriched_entities lacks `cnpj_8` column for direct join with bids/contracts
- 12-day gap since last bid publication (2026-06-29)

## Indexes

37 indexes total. Key ones: hnsw embedding index, gin full-text search, gist trigram, btree UF+date with partial WHERE is_active. Good coverage.

## Recommendations

1. Reset stuck runs: `UPDATE ingestion_runs SET status='failed' WHERE status='running' AND started_at < NOW() - INTERVAL '1 hour';`
2. Debug why ingestion_checkpoints never populates.
3. Add date constraint or app-level validation for contract data_assinatura.
4. Extract cnpj_8 from enriched_entities JSONB if join perf matters.
