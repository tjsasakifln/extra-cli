# Operational Limits — Live Backfill DB (`5433`)

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Subagent:** E (Performance)  
**Date:** 2026-07-22  
**Writer under protection:** HC Closure `run_contracts_90d_pilot` → `extra_test@127.0.0.1:5433`

---

## 1. Hard rules (non-negotiable)

| Rule | Detail |
|------|--------|
| **No writes** | No DML/DDL/VACUUM FULL/REINDEX/REFRESH from this campaign on 5433 |
| **No restart** | Do not docker restart `extraconsultoria-test-db-1` |
| **No checkpoint touch** | Never write `data/contracts_checkpoints/hc_closure_*` |
| **No migration apply** to 5433 from this campaign | Use `NATIONAL_INTEL_DSN` → **5435** |
| **No national re-backfill** | Non-goal of this architecture campaign |

Violation = collision with `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01`.

---

## 2. When **not** to run heavy `EXPLAIN ANALYZE`

### Forbidden / strongly discouraged on live writer

| Operation | Why it hurts |
|-----------|--------------|
| `EXPLAIN ANALYZE` on full-table or multi-million aggregates | Executes the plan: CPU, buffer thrash, longer lock/snapshot duration |
| `EXPLAIN ANALYZE` with sorts spilling to disk | Competes with upsert I/O |
| `SELECT count(*)` without index-only path on whole table | Seq scan under concurrent inserts |
| `SELECT * FROM pncp_supplier_contracts` large OFFSET | Useless load |
| `CREATE INDEX` / `REINDEX` / `VACUUM FULL` | Locks or massive I/O |
| `REFRESH MATERIALIZED VIEW` | Exclusive or heavy concurrent I/O |
| `ANALYZE pncp_supplier_contracts` during peak write | Extra I/O; planner stats can wait until quiet |
| Long open transactions (idle in transaction) | Blocks vacuum; bloat |

### Especially dangerous query shapes

```sql
-- DO NOT on 5433 during backfill
EXPLAIN ANALYZE
SELECT fornecedor_cnpj, sum(valor_total)
FROM pncp_supplier_contracts
GROUP BY 1
ORDER BY 2 DESC;

EXPLAIN ANALYZE
SELECT * FROM pncp_supplier_contracts
WHERE objeto_contrato ILIKE '%x%';  -- may still touch large bitmap under load
```

### Safer alternatives

| Goal | Do this instead |
|------|-----------------|
| Plan shape only | `EXPLAIN (FORMAT TEXT)` **without** `ANALYZE` — still non-zero cost but no execution |
| True timing | Restore dump to **5435** or throwaway DB; then `EXPLAIN ANALYZE` |
| Row estimate | `pg_stat_user_tables.n_live_tup` (catalog; cheap) |
| Size | `pg_relation_size` / `pg_total_relation_size` — short catalog calls |
| Product logic | Fixture data on 5435 + unit tests |

---

## 3. Read-only ops allowed (if indispensable)

From isolation plan: default **none**; if needed, short and lock-light.

| Allowed (short) | Notes |
|-----------------|-------|
| `SELECT pg_is_in_recovery()` | health |
| `SELECT count(*) FROM pg_stat_activity` | filter by datname |
| `pg_relation_size('pncp_supplier_contracts')` | milliseconds |
| `SELECT reltuples FROM pg_class WHERE relname = ...` | estimate only |
| Single-row PK / `contrato_id` lookup with `LIMIT 1` | verify connectivity |

| Soft limit | Guidance |
|------------|----------|
| Query wall time | abort if > **2s** expected |
| Concurrent campaign sessions | ≤ 1 ad-hoc reader |
| Time of day | avoid if backfill log shows API burst / DB CPU high |

---

## 4. When heavy analysis **is** allowed

| Condition | OK to |
|-----------|-------|
| HC PID finished or paused by **its** owners | deeper stats on 5433 |
| Logical dump restored elsewhere | full `EXPLAIN ANALYZE`, index experiments |
| Isolated `5435` with fixtures / sample | always for this campaign |
| Separate analytics replica (future VPS) | marts, vacuum tuning |

---

## 5. Host-level contention (shared machine)

Even “read-only” competes for:

- Disk bandwidth (Docker volume on same host as HC)
- CPU with Python crawler PID
- Memory (Postgres `shared_buffers` + OS page cache)

**Prefer:** zero traffic to 5433 from architecture campaign; all design validated via schema files + 5435.

---

## 6. Autovacuum / maintenance blackout

During continuous upsert:

| Action | Guidance |
|--------|----------|
| Manual `VACUUM` | only if ops declares emergency bloat **and** owns HC risk |
| `VACUUM FULL` | **never** during backfill (rewrite + exclusive lock) |
| `REINDEX` | post-backfill maintenance window |
| Drop/create GIN | post-backfill; see index recommendations |
| Backup full DB | post-quiesce; multi-GB dump steals I/O |

---

## 7. Observability without harm

Prefer HC campaign’s own artifacts:

- Checkpoint JSON (read-only path in **their** tree)
- `live-3y.log` / output JSON under HC artifacts
- `docker logs` / `pg_stat_activity` snapshots already in safety inventory

Do not open long `psql` sessions “just in case.”

---

## 8. Decision tree (quick)

```text
Need performance number?
  ├─ Schema / index existence? → read current-schema.sql / migrations
  ├─ Row/size ballpark? → use inventory snapshot OR one pg_*_size call
  ├─ EXPLAIN shape? → EXPLAIN without ANALYZE, or isolated restore
  ├─ EXPLAIN ANALYZE / CREATE INDEX / MV? → NOT on 5433 until writer idle
  └─ Product feature test? → 5435 fixtures only
```

---

## 9. Cross-links

- Safety: `../safety/database-isolation.md`, `../safety/active-process-inventory.md`, `../safety/collision-matrix.md`
- Growth: `./storage-growth-estimate.md`
- Indexes: `./index-recommendations.md`
- MVs: `./materialization-strategy.md`
- Backup: `./vps-readiness.md`
)
