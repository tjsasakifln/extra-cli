# Materialization Strategy — Risks, Refresh, Bloat

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Subagent:** E (Performance)  
**Date:** 2026-07-22  
**Constraint:** Design-only — no new MVs on live HC DB (`5433`)

---

## 1. Existing materialization in repo

| Object | Source | Role |
|-------|--------|------|
| `mv_entity_source_applicability` | `db/migrations/040_coverage_model_expansion.sql` | Entity × source applicability matrix for coverage model |
| Unique index | `(entity_id, source)` | Enables `REFRESH MATERIALIZED VIEW CONCURRENTLY` |
| Ordinary views | many `v_*` on contracts | No storage; recompute each query |

**Lesson from 040:** coverage-scale MVs are acceptable when:

1. Cardinality is **entities × sources** (thousands–tens of thousands), not **contracts** (millions).  
2. Unique index exists for concurrent refresh.  
3. Refresh is **scheduled / on-demand**, not per API hit.

---

## 2. Candidate analytical marts (national intelligence)

| Mart (proposed name) | Grain | Purpose | Cardinality order |
|----------------------|-------|---------|-------------------|
| `intel.mv_supplier_uf_monthly` | supplier × UF × month | competitors, trends | 10^5–10^6 |
| `intel.mv_orgao_monthly` | orgao_cnpj_8 × month | agency profiles | 10^5 |
| `intel.mv_uf_value_histogram` | UF × bucket × month | value distributions | 10^4 |
| `intel.mv_top_suppliers_uf` | UF × rank | precomputed top-N | 27 × N |

Prefer schema `intel` (isolation plan) or prefix `mv_intel_*` pending ADR.

**Rule:** materialize **aggregates**, never a second full copy of `pncp_supplier_contracts` unless OLAP isolation (columnar / separate warehouse) is an explicit product decision.

---

## 3. Refresh cost model

### 3.1 `REFRESH MATERIALIZED VIEW` (non-concurrent)

| Property | Behavior |
|----------|----------|
| Lock | **AccessExclusive** on the MV — readers block |
| Cost | Full recompute from base tables |
| On contracts join | Can scan **millions** of rows → minutes to tens of minutes at 6M+ |
| During HC backfill | **Forbidden** if base table is under heavy upsert on same instance |

### 3.2 `REFRESH MATERIALIZED VIEW CONCURRENTLY`

| Property | Behavior |
|----------|----------|
| Lock | Allows SELECTs; needs **UNIQUE index** on MV |
| Cost | Often **higher** total I/O than non-concurrent (builds new data + merges) |
| Bloat | Can leave dead tuples; needs periodic `VACUUM` on MV |
| Failure mode | Fails if unique index missing or duplicates appear |

### 3.3 Estimated refresh wall time (order of magnitude)

Assumptions: cold-ish cache, single mid-tier CPU, full scan of contracts for group-by.

| Base rows | Simple GROUP BY (supplier×UF×month) | Concurrent refresh |
|-----------|--------------------------------------|--------------------|
| 2.3M | ~1–5 min | ~2–10 min |
| 6M | ~5–20 min | ~10–40 min |
| 10M | ~10–40 min | ~20–60+ min |

**These are planning envelopes, not benchmarks.** Measure on restored snapshot.

### 3.4 Incremental alternatives (preferred at national scale)

| Pattern | Pros | Cons |
|---------|------|------|
| **Incremental fact table** (`intel.contract_facts_daily`) maintained by pipeline after upsert window | cheap refresh | more application logic |
| **Partitioned monthly tables** + per-partition aggregate | prune history | migration complexity |
| **Nightly batch job** on replica / isolated analytics DB | zero impact on writer | staleness 24h |
| **No MV** — query with good indexes for UF-scoped | freshest | limited for national rollups |

For this product: **nightly marts on non-writer** beat concurrent MV on the ingestion primary.

---

## 4. Bloat risks

| Risk | Mechanism | Mitigation |
|------|-----------|------------|
| MV bloat after CONCURRENTLY | dead tuples from merge | `VACUUM (VERBOSE)` / autovacuum tune on MV |
| Base table bloat under continuous upsert | HOT updates limited by indexed column churn | autovacuum scale factor lower for `pncp_supplier_contracts`; avoid dual GIN |
| Index bloat on GIN | text updates / reindex needs | `REINDEX INDEX CONCURRENTLY` in maintenance window |
| WAL spike on refresh | full rewrite | schedule off-peak; ensure disk for WAL |
| “Stale truth” product risk | MV lag vs live contracts | stamp `refreshed_at`; UI labels “as of” |

### Autovacuum note (base table, not only MVs)

National upsert volume will produce dead tuples if `is_active` flips or updates rewrite rows. Monitor:

```sql
SELECT relname, n_live_tup, n_dead_tup, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'pncp_supplier_contracts';
```

Only on idle / replica — not during critical backfill pages.

---

## 5. Decision matrix: MV vs view vs app cache

| Need | Prefer |
|------|--------|
| Interactive filter SC-only, selective | Ordinary view + btree/GIN (current) |
| National top-N competitors dashboard | **Mart / MV** refreshed nightly |
| Coverage applicability (entity×source) | Existing MV pattern (040) — small grain |
| Exact live row for one CNPJ | Base table index path |
| PDF/Excel batch reports | Snapshot query on restore or mart (stable numbers) |

---

## 6. Safe design checklist before any MV ships

1. [ ] Grain and unique key documented  
2. [ ] Unique index for concurrent refresh **or** explicit exclusive refresh window  
3. [ ] Refresh owner: systemd timer / ops job (not request path)  
4. [ ] `refreshed_at` column or comment + monitoring  
5. [ ] Estimated size = f(cardinality) stored in ADR  
6. [ ] Refresh tested on **5435** or restore DB, never first-try on writer under load  
7. [ ] Rollback: `DROP MATERIALIZED VIEW` does not drop base contracts  
8. [ ] Product copy never claims “real-time national” if nightly  

---

## 7. Explicit non-actions for this campaign wave

- Do **not** create national contract MVs on `5433`  
- Do **not** `REFRESH` existing MVs on the HC database while PID backfill runs  
- Do **not** treat empty `5435` as performance proof of MV refresh  

---

## 8. References

- MV definition: `db/migrations/040_coverage_model_expansion.sql`  
- Isolation plan: `artifacts/campaigns/.../safety/database-isolation.md`  
- Storage bands: `./storage-growth-estimate.md`  
- Index support: `./index-recommendations.md`
)
