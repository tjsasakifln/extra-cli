# Index Strategy Recommendations — Analytical National Contracts

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Subagent:** E (Performance)  
**Date:** 2026-07-22  
**Constraint:** **Recommendations only** — do **not** apply to `extra_test:5433` during HC backfill  
**Target for future apply:** isolated DB `5435` / future national intel schema after Spec + ADR

---

## 1. Current index inventory (from `db/current-schema.sql`)

On `pncp_supplier_contracts`:

| Index | Definition | Serves |
|-------|------------|--------|
| `pncp_supplier_contracts_pkey` | PK `(id)` | identity |
| `pncp_supplier_contracts_contrato_id_key` | UNIQUE `(contrato_id)` | upsert / dedup |
| `idx_psc_uf` | `(uf, data_publicacao DESC)` | UF + time filters |
| `idx_psc_data` | `(data_publicacao DESC)` | pure time |
| `idx_psc_fornecedor` | `(fornecedor_cnpj, data_publicacao DESC)` | supplier timeline |
| `idx_psc_orgao` | `(orgao_cnpj)` | agency filter |
| `idx_psc_valor` | `(valor_total)` | value sort/filter |
| `idx_contracts_fornecedor_cnpj_8` | partial `(fornecedor_cnpj_8)` | entity join (base-8) |
| `idx_contracts_fornecedor_cnpj_lookup` | partial `(fornecedor_cnpj)` | full CNPJ lookup |
| `idx_contracts_orgao_cnpj_8` | partial `(orgao_cnpj_8)` | entity join (base-8) |
| `idx_psc_objeto_contrato_gin` | GIN trgm partial `is_active` | ILIKE object search |
| `idx_psc_objeto_trgm` | GIN trgm **full** | same column, broader |

**Assessment:** Operational CRUD + SC-oriented access paths are already covered. National **analytical** workloads (top competitors by UF, agency profiles, value distributions) need **composite / covering** patterns and **index hygiene** (duplicate GIN).

---

## 2. Analytical query families (product-facing)

Aligned with deliverables A/B/D patterns and market intel products:

| Family | Typical predicate | Aggregate |
|--------|-------------------|-----------|
| **Competitors by UF** | `uf = $1`, optional date range, `fornecedor_cnpj IS NOT NULL` | `COUNT(*)`, `SUM(valor_total)`, top-N suppliers |
| **Value distributions** | `uf`, date, optional modality/source | histogram buckets, percentiles, ticket médio |
| **Agency profiles** | `orgao_cnpj` / `orgao_cnpj_8`, date | spend, supplier diversity, object themes |
| **Supplier deep-dive** | `fornecedor_cnpj` / `_8` | orgs won, geo spread, value over time |
| **Object search** | `objeto_contrato ILIKE` / trgm | filtered lists |
| **Active portfolio** | `is_active`, `data_fim` | vigência windows |

---

## 3. Recommendations (priority ordered)

### P0 — Hygiene (storage + write amplification)

#### R1. Rationalize dual GIN on `objeto_contrato`

**Problem:** Both `idx_psc_objeto_trgm` (full) and `idx_psc_objeto_contrato_gin` (partial `is_active`) index the same text with `gin_trgm_ops`. At multi-million rows this is **major write and storage cost** during every upsert that touches `objeto_contrato`.

**Recommendation:**

- Keep **one** GIN:
  - Prefer **partial** `WHERE is_active = TRUE` if product queries always filter active; **or**
  - Prefer **full** if inactive rows must be searchable for history.
- Drop the redundant index in a **dedicated maintenance window** with `DROP INDEX CONCURRENTLY` after proving EXPLAIN parity on isolated restore.

**Do not run on 5433 while backfill writes.**

#### R2. Avoid new non-CONCURRENTLY indexes on live large tables

All future creates:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ...
```

Never in a transaction block with other DDL. Prefer isolated DB first.

---

### P1 — Composites for analytical filters

#### R3. Competitors by UF (hot path)

```sql
-- RECOMMENDED (isolated / post-HC only)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_uf_fornecedor_valor
  ON pncp_supplier_contracts (uf, fornecedor_cnpj, valor_total DESC)
  WHERE fornecedor_cnpj IS NOT NULL AND is_active = TRUE;
```

**Why:** Supports `WHERE uf = $1 GROUP BY fornecedor_cnpj ORDER BY SUM(valor_total)` and top-N patterns used by competitor mapping (Deliverable B style). Existing `idx_psc_uf` helps filter but does not co-locate supplier+value.

**Alternative lighter form** if partial too narrow:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_uf_fornecedor
  ON pncp_supplier_contracts (uf, fornecedor_cnpj)
  WHERE fornecedor_cnpj IS NOT NULL;
```

#### R4. Agency profile + time

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_orgao8_data
  ON pncp_supplier_contracts (orgao_cnpj_8, data_publicacao DESC)
  WHERE orgao_cnpj_8 IS NOT NULL;
```

**Why:** Generated `orgao_cnpj_8` is the join key to `sc_public_entities` / entity marts. Current `idx_psc_orgao` is full CNPJ only; profiles and entity-scoped spend benefit from base-8 + time.

#### R5. Supplier profile + time (if `idx_psc_fornecedor` insufficient under national volume)

Existing `(fornecedor_cnpj, data_publicacao DESC)` is already strong. Prefer **`fornecedor_cnpj_8` composite** for entity-level rollups:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_forn8_data
  ON pncp_supplier_contracts (fornecedor_cnpj_8, data_publicacao DESC)
  WHERE fornecedor_cnpj_8 IS NOT NULL;
```

---

### P2 — Value distributions

#### R6. Prefer BRIN for pure chronological bulk analytics (optional)

At multi-million insert-mostly historical loads, if `data_publicacao` is roughly insert-correlated:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_data_brin
  ON pncp_supplier_contracts USING brin (data_publicacao)
  WITH (pages_per_range = 32);
```

**When:** large range scans (`WHERE data_publicacao BETWEEN ...`) over national history; cheap storage.  
**When not:** selective point lookups (keep btree `idx_psc_data`).

#### R7. Value filters with UF (not bare `valor_total` alone)

Bare `idx_psc_valor` rarely helps “top contracts in SC last 12 months” without UF/time. Prefer:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_uf_data_valor
  ON pncp_supplier_contracts (uf, data_publicacao DESC, valor_total DESC)
  WHERE is_active = TRUE;
```

Use for agency/competitor reports constrained by geography + period.

#### R8. Percentiles / histograms

PostgreSQL will often **seq scan + hashagg** for global percentiles on 6M rows. Prefer:

1. Pre-aggregate daily/monthly marts (see `materialization-strategy.md`), **or**
2. Approximate with sampled queries on replica / offline restore, **or**
3. `percentile_disc` on **UF-scoped** subsets that hit R3/R7 indexes.

**Do not** add a pure `(valor_total)` expression index expecting magic for national histograms.

---

### P3 — Covering / INCLUDE (PostgreSQL 11+)

#### R9. Index-only scans for ranking lists

If EXPLAIN shows heap fetches dominating after filter:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_uf_forn_covering
  ON pncp_supplier_contracts (uf, fornecedor_cnpj)
  INCLUDE (valor_total, data_publicacao, orgao_cnpj)
  WHERE is_active = TRUE AND fornecedor_cnpj IS NOT NULL;
```

**Trade-off:** larger index; only add after measuring R3 alone is insufficient.

---

### P4 — Explicit non-goals

| Do not | Why |
|--------|-----|
| Hash indexes | poor for ranges; maintenance cost |
| Extra GIN on `orgao_nome` / `fornecedor_nome` without product need | write amplification |
| Expression indexes with non-immutable functions | planner rejection / bloat |
| Full-table `CREATE INDEX` without CONCURRENTLY on prod | locks writers |
| Applying any of the above on **5433 during HC** | write + I/O contention |

---

## 4. Query sketch → index map

```sql
-- Competitors by UF (top 15)
SELECT fornecedor_cnpj, COUNT(*) AS n, SUM(valor_total) AS v
FROM pncp_supplier_contracts
WHERE uf = $1 AND is_active AND fornecedor_cnpj IS NOT NULL
  AND data_publicacao >= $2
GROUP BY 1
ORDER BY v DESC NULLS LAST
LIMIT 15;
-- Prefer: R3 or R7; fallback idx_psc_uf + filter

-- Agency profile
SELECT date_trunc('month', data_publicacao) AS m,
       COUNT(*), SUM(valor_total), COUNT(DISTINCT fornecedor_cnpj)
FROM pncp_supplier_contracts
WHERE orgao_cnpj_8 = $1 AND data_publicacao BETWEEN $2 AND $3
GROUP BY 1 ORDER BY 1;
-- Prefer: R4

-- Value distribution (UF-scoped buckets)
SELECT width_bucket(valor_total, 0, 1e7, 20) AS b, COUNT(*)
FROM pncp_supplier_contracts
WHERE uf = $1 AND valor_total IS NOT NULL AND is_active
GROUP BY 1;
-- Prefer: idx_psc_uf (+ heap) or mart; not bare idx_psc_valor
```

---

## 5. Application procedure (when authorized)

1. Spec Kit + ADR approve analytical access paths.  
2. Build on **isolated** `5435` with fixture or **post-HC** snapshot restore — never on live writer.  
3. `CREATE INDEX CONCURRENTLY` one at a time; monitor disk (`pg_indexes_size`).  
4. Validate with `EXPLAIN (ANALYZE, BUFFERS)` **only** on non-writer DB.  
5. Update `db/migrations/` additively; never rewrite baseline casually.  
6. Drop redundant GIN only after dual EXPLAIN proof + backup.

---

## 6. Expected storage impact (order of magnitude)

| Change | Disk delta @ ~6M rows (order) |
|--------|-------------------------------|
| Drop redundant full GIN | **save** multi-GB (largest win) |
| R3 composite UF+supplier | ~0.5–1.5 GB |
| R4 orgao8+data | ~0.3–0.8 GB |
| R7 uf+data+valor | ~0.5–1.2 GB |
| BRIN data | tens of MB |

Net: hygiene first can **fund** 2–3 new composites.

---

## 7. References

- Schema: `db/current-schema.sql`  
- TD GIN story: `docs/td-001/query-optimization.md`, migration `013`  
- Competitor product shape: `scripts/ops/deliverable_b_competitors.py`  
- Org ranking: `scripts/ops/deliverable_a_org_ranking.py`  
- Isolation: `artifacts/campaigns/.../safety/database-isolation.md`
)
