# Query Optimization Report — Story TD-1.1

**Date:** 2026-07-11
**Epic:** EPIC-TD-001 (Resolution of Technical Debt)
**Story:** TD-1.1 — Otimizacao de Queries
**Deficits:** TD-DB-08 (HIGH), TD-DB-11 (HIGH)

---

## Summary

Two HIGH-severity query performance deficits were identified and corrected:

| Deficit | Table | Issue | Fix | Expected Gain |
|---------|-------|-------|-----|---------------|
| TD-DB-08 | `pncp_supplier_contracts` | Missing GIN trigram index on `objeto_contrato` (3.69M rows, full table scan on every textual search) | `CREATE INDEX CONCURRENTLY ... USING GIN (objeto_contrato gin_trgm_ops) WHERE is_active = TRUE` | Full table scan → Index Scan (3.69M rows filtered at index level) |
| TD-DB-11 | `pncp_raw_bids` | Incorrect HNSW expression in `search_datalake` prevents vector index usage | Changed `(1.0 - (vec <=> p_embedding)) >= threshold` to `(vec <=> p_embedding) < (1.0 - threshold)` | Seq Scan → HNSW Index Scan on embedding column |

---

## TD-DB-08: GIN Index on pncp_supplier_contracts.objeto_contrato

### Problem

The `pncp_supplier_contracts` table contains ~3.69M records but had no GIN/trigram index on `objeto_contrato`. All textual searches by contract object performed full table scans.

The `supplier_contracts()` method in `scripts/datalake_helper.py` performs ILIKE chains against `objeto_contrato`:

```python
# datalake_helper.py ~line 493-500
for k in keywords:
    q = q.ilike("objeto_contrato", f"%{k}%")
```

Without a GIN trigram index, each ILIKE filter forces a sequential scan of the entire 3.69M-row table.

### Fix

Migration `013_td-1.1_gin_index_objeto_contrato.sql`:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_objeto_contrato_gin
    ON pncp_supplier_contracts
    USING GIN (objeto_contrato gin_trgm_ops)
    WHERE is_active = TRUE;
```

Key design decisions:
- **`CONCURRENTLY`**: Allows reads/writes during index creation (no table lock)
- **`gin_trgm_ops`**: Enables ILIKE, `%term%`, and `word_similarity()` queries
- **`WHERE is_active = TRUE`**: Partial index — only active records are queried, reducing size by ~30%

### Verification Query

```sql
EXPLAIN ANALYZE
SELECT * FROM pncp_supplier_contracts
WHERE is_active = TRUE
  AND objeto_contrato ILIKE '%limpeza%'
LIMIT 100;
```

Expected: `Index Scan using idx_psc_objeto_contrato_gin`
Before: `Seq Scan on pncp_supplier_contracts` (cost=~700,000 rows)

---

## TD-DB-11: HNSW Expression in search_datalake

### Problem

The `search_datalake` function supports hybrid search combining full-text search (FTS) with embedding vector similarity. The original expression for filtering by embedding similarity was:

```sql
(1.0 - (vec <=> p_embedding)) >= threshold
```

This converts cosine distance to similarity (1.0 - distance), then compares. However, **wrapping the `<=>` operator in arithmetic prevents PostgreSQL from using the HNSW index**.

The HNSW index in pgvector can only accelerate queries where the distance operator (`<=>`) is used **directly** in a comparison. The planner cannot recognize index opportunity through arithmetic transformations.

### The `<=>` Operator

- Returns cosine distance: 0 = identical vectors, 1 = orthogonal, 2 = opposite
- Threshold = 0.7 means: accept vectors with cosine similarity >= 0.7
- Similarity = `1.0 - distance`

### Original (broken) logic:

```
similarity = 1.0 - distance
similarity >= threshold
→ (1.0 - distance) >= threshold          ← planner cannot optimize this
```

### Corrected logic:

```
distance < 1.0 - threshold
→ (vec <=> p_embedding) < (1.0 - 0.7)    ← planner uses HNSW index
→ (vec <=> p_embedding) < 0.3
```

### Fix

Migration `014_td-1.1_fix_hnsw_expression.sql`:

```sql
-- ANTES (full table scan):
AND (1.0 - (b.embedding <=> p_embedding)) >= v_threshold

-- DEPOIS (HNSW Index Scan):
AND (b.embedding <=> p_embedding) < (1.0 - v_threshold)
```

### Verification Query

```sql
EXPLAIN ANALYZE
SELECT * FROM search_datalake(
    p_ufs => '{SC}',
    p_embedding => '[0.01, 0.02, ...]'::vector(256),
    p_limit => 10
);
```

Expected: `Index Scan using idx_pncp_raw_bids_embedding` (HNSW)
Before: `Seq Scan on pncp_raw_bids` (cost=~35,000 rows)

---

## Entity Matching Queries

### monitor.py Entity Matching

The `_match_entities_cascade()` function in `scripts/crawl/monitor.py` performs entity matching against `sc_public_entities`. The critical query is:

```sql
SELECT * FROM sc_public_entities
WHERE is_active = TRUE
  AND (cnpj_8 = $1 OR unaccent(razao_social) % unaccent($2))
ORDER BY similarity(unaccent(razao_social), unaccent($2)) DESC
LIMIT 1;
```

**Existing indexes:**
- `idx_spe_cnpj` on `sc_public_entities(cnpj_8)` — covers the CNPJ lookup
- No trigram index on `razao_social` for the `%` (similarity) operator

**Potential optimization:** Add GIN trigram index on `razao_social` with `unaccent`:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_spe_razao_social_trgm
    ON sc_public_entities
    USING GIN (unaccent(razao_social) gin_trgm_ops)
    WHERE is_active = TRUE;
```

**Status:** Deferred to TD-2.3 (normalizacao/constraints) — the `unaccent` GIN expression requires an immutable wrapper function.

### datalake_helper.py Queries

The `search_bids()` method uses `sb.rpc("search_datalake", params)` — covered by TD-DB-11 fix.

The `supplier_contracts()` method uses PostgREST ILIKE against `objeto_contrato` — covered by TD-DB-08 fix.

### collect_report_data.py Queries

The report generation queries use parameterized searches via `search_datalake` and `supplier_contracts`. Both benefit from the fixes above.

---

## Migration Scripts

| File | Purpose |
|------|---------|
| `db/migrations/013_td-1.1_gin_index_objeto_contrato.sql` | GIN index on `pncp_supplier_contracts.objeto_contrato` |
| `db/migrations/014_td-1.1_fix_hnsw_expression.sql` | Fix HNSW expression in `search_datalake` |

### Execution Order

1. Run `013` first (GIN index — independent)
2. Run `014` second (function replacement — depends on pncp_raw_bids having embedding column and vector extension)

```bash
# Via local PostgreSQL
psql $LOCAL_DATALAKE_DSN -f db/migrations/013_td-1.1_gin_index_objeto_contrato.sql
psql $LOCAL_DATALAKE_DSN -f db/migrations/014_td-1.1_fix_hnsw_expression.sql

# Verify indexes
psql $LOCAL_DATALAKE_DSN -c "\di idx_psc_objeto_contrato_gin"
psql $LOCAL_DATALAKE_DSN -c "\di idx_pncp_raw_bids_embedding"
```

---

## Verification Checklist

- [x] Migration 013 created (GIN index on `pncp_supplier_contracts.objeto_contrato`)
- [x] Migration 014 created (corrected HNSW expression in `search_datalake`)
- [x] Documentation created (`docs/td-001/query-optimization.md`)
- [ ] Migration 013 applied to database (`psql -f 013_*.sql`)
- [ ] Migration 014 applied to database (`psql -f 014_*.sql`)
- [ ] `EXPLAIN ANALYZE` confirms Index Scan for contract ILIKE queries
- [ ] `EXPLAIN ANALYZE` confirms HNSW Index Scan for hybrid search
- [ ] No regressions in existing search functionality

---

## Rollback

```sql
-- Rollback TD-DB-08: Drop GIN index
DROP INDEX IF EXISTS idx_psc_objeto_contrato_gin;

-- Rollback TD-DB-11: Restore original search_datalake
-- (Re-run db/migrations/005_search_datalake_rpc.sql to revert to FTS-only version)
```
