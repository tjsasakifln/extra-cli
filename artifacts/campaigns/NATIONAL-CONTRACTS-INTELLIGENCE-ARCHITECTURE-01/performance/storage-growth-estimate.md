# Storage Growth Estimate — National 3y Contracts

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Subagent:** E (Performance / Storage)  
**Date:** 2026-07-22  
**Mode:** Projection only — no DDL, no heavy scans on live backfill DB  
**Primary table:** `public.pncp_supplier_contracts`

---

## 1. Observed mid-run baseline (do not treat as final)

| Source | Metric | Value |
|--------|--------|--------|
| HC checkpoint `hc_closure_3y` | `total_contracts_fetched` | **1,517,280** |
| HC checkpoint | `completed_windows` | **19** |
| HC checkpoint | `total_windows_failed` | **4** |
| HC command | `--days 1098` (~3y) | window |
| Window size | `CONTRACTS_WINDOW_DAYS` default | **30** days (`scripts/crawl/contracts_crawler.py`) |
| Isolation inventory | live rows on `extra_test:5433` | **~2.27M** |
| Isolation inventory | table heap ≈ | **~2.5 GB** |
| Isolation inventory | full DB ≈ | **~2.6 GB** |
| Pilot docstring | national volume heuristic | **~500k contracts / 90d** |

### Interpretation of the gap (fetched vs live rows)

- Live rows (**~2.27M**) > fetched this run (**~1.52M**): table already held historical/SC rows before or concurrent with HC.
- Upsert is by `contrato_id` (unique): fetch count is **API volume processed**, not necessarily net new rows.
- Failed windows (4) mean planned coverage is incomplete; retries will re-fetch some ranges.

**Do not claim “2.27M = national 3y complete.”** It is mid-run + residual prior data.

---

## 2. Planned window arithmetic (3y)

| Parameter | Calculation | Result |
|-----------|-------------|--------|
| Span | 1098 days | ~3.0 years |
| Window | 30 days | default |
| Planned windows (approx.) | `ceil(1098 / 30)` | **~37** |
| Progress (windows complete only) | 19 / 37 | **~51%** of calendar windows |
| Progress (with failures) | 19 ok + 4 failed | incomplete; not “half done” as success |

### Throughput so far (fetched / completed windows)

| Metric | Value |
|--------|--------|
| Avg contracts/window (fetched) | 1,517,280 / 19 ≈ **79.9k** |
| Avg contracts/day (fetched) | ≈ **2.66k** (if 19×30 = 570 days covered) |
| Documented national heuristic | 500k / 90d ≈ **5.56k/day** ≈ **167k / 30d window** |

Current mid-run rate is **~0.5×** the pilot’s national heuristic. Possible causes: quieter historical windows, page errors/partial pages not fully counted as success, geographic/time skew, or heuristic overestimate. **Both rates are retained as scenarios.**

---

## 3. Row-count completion scenarios

### Scenario A — Linear extrapolation of current HC rate (conservative mid-run)

| Step | Estimate |
|------|----------|
| Remaining windows | ~18 (37 − 19), ignoring retries of 4 failed |
| Extra fetch @ ~80k/window | ~1.4M |
| Total **fetched** by end of run | **~2.9–3.2M** |
| Net live rows | depends on prior data + dedup; **~3.0–3.5M** plausible if most fetches insert |

### Scenario B — Pilot national heuristic (planning envelope)

| Step | Estimate |
|------|----------|
| 1098d × 5.56k/day | **~6.1M** contracts |
| Or 37 windows × 167k | **~6.2M** |
| Planning band | **5.5–7.0M** unique national contracts over 3y |

### Scenario C — Historical TD-001 reference (context only)

| Source | Rows cited |
|--------|------------|
| `docs/td-001/query-optimization.md` | **~3.69M** on `pncp_supplier_contracts` |

Treat as a **prior environment snapshot**, not as a promise of this HC run’s final count. Useful as a mid-band sanity check between A and B.

### Recommended planning target for architecture

| Horizon | Rows (planning) | Notes |
|---------|-----------------|--------|
| HC run complete (local `extra_test`) | **3.0–4.0M** | Scenario A + retries + residual prior |
| National 3y intelligence product | **5.5–7.0M** | Scenario B envelope |
| Stress / headroom (indexes + growth + bloat) | **8–10M** | capacity design, not a forecast |

---

## 4. Bytes-per-row and storage projection

### Schema drivers (`db/current-schema.sql`)

Columns include text-heavy fields (`objeto_contrato`, names, CNPJs), `numeric(18,2)`, dates, generated `orgao_cnpj_8` / `fornecedor_cnpj_8`, and multiple indexes:

| Index (existing) | Type | Role |
|------------------|------|------|
| PK `id` | btree | identity |
| UNIQUE `contrato_id` | btree | upsert dedup |
| `idx_psc_uf` | btree `(uf, data_publicacao DESC)` | geo-time |
| `idx_psc_data` | btree `data_publicacao DESC` | time |
| `idx_psc_fornecedor` | btree `(fornecedor_cnpj, data_publicacao DESC)` | competitor |
| `idx_psc_orgao` | btree `orgao_cnpj` | agency |
| `idx_psc_valor` | btree `valor_total` | value |
| `idx_contracts_*_cnpj_8` | partial btree | entity join |
| `idx_psc_objeto_contrato_gin` | GIN trgm partial `is_active` | ILIKE |
| `idx_psc_objeto_trgm` | GIN trgm **full** | **overlaps partial GIN** |

### Observed density (mid-run)

| Quantity | Value |
|----------|--------|
| Live rows | ~2.27M |
| Heap ≈ | ~2.5 GB |
| **Heap bytes/row** | ~2.5e9 / 2.27e6 ≈ **1.1 KB/row** |

Indexes are **not** fully measured in this pass (avoid heavy catalog scans during backfill). For multi-btree + dual-GIN text tables, a working ratio is:

| Component | Multiplier vs heap | Notes |
|-----------|-------------------|--------|
| Heap | 1.0× | includes TOAST for long `objeto_contrato` |
| Indexes (all) | **0.7–1.3×** heap | GIN dominates |
| Total relation | **1.7–2.3×** heap | planning band |

At 2.27M / 2.5 GB heap, if total relation (heap+indexes) is ~1.8–2.2×, indexes alone may already be **~2–3 GB** — consistent with “table ~2.5 GB” inventory focusing on heap and “DB ~2.6 GB” if other relations are small **or** inventory “2.5 GB” already approximated total. **Uncertainty: ±40% until post-backfill `pg_total_relation_size`.**

### Storage bands by row count

Assumptions: **1.1 KB heap/row**; total relation **2.0× heap** (mid); full DB = contracts + other tables (bids, entities, opportunity_intel, checkpoints) **1.4–2.0×** contracts total.

| Scenario | Rows | Heap | Relation (heap+idx) | Full DB band |
|----------|------|------|---------------------|--------------|
| Current mid-run | 2.3M | ~2.5 GB | ~4–6 GB* | ~2.6–7 GB* |
| A — HC complete | 3.5M | ~3.9 GB | ~7–9 GB | ~10–15 GB |
| C — TD-001 mid | 3.7M | ~4.1 GB | ~7–10 GB | ~10–16 GB |
| B — national 3y | 6.2M | ~6.8 GB | **12–16 GB** | **18–28 GB** |
| Stress headroom | 10M | ~11 GB | **20–25 GB** | **30–45 GB** |

\*Mid-run full-DB inventory (~2.6 GB) suggests either indexes are still smaller than the mid multiplier, many indexes not yet fully built on all data, or the 2.5 GB figure is total-relation-ish. **Re-measure after HC finishes and after `ANALYZE`.**

### Growth drivers beyond row count

| Driver | Effect |
|--------|--------|
| Long `objeto_contrato` | TOAST bloat; GIN size tracks text volume |
| Dual GIN on same column | **~2× text-index storage** vs one GIN — candidate rationalization (see `index-recommendations.md`) |
| `contract_version_history` | multiplies storage if versioning enabled at scale |
| `pncp_raw_bids` + embeddings | can exceed contracts if HNSW vectors retained nationally |
| WAL during bulk upsert | temporary disk for checkpoints/WAL — size for **≥2×** peak write bursts |
| Autovacuum lag | dead tuples during continuous upsert inflate heap until vacuum |

---

## 5. Time-to-completion (operational, not a guarantee)

| Input | Value |
|-------|--------|
| Elapsed at inventory | ~6h for ~1.52M fetched + 19 windows |
| Remaining windows | ~18 + 4 failed retries |
| Rough remaining wall time | order of **several more hours to 1+ day** if rate holds; API 400s (page 186) can stretch this |

**Not a SLA.** Rate is PNCP-limited and error-sensitive. Architecture must not depend on “done by date X.”

---

## 6. Capacity recommendations (local + VPS)

| Environment | Guidance |
|-------------|----------|
| Local Docker (`5433` / HC) | Leave volume alone until backfill ends; ensure host free disk **≥ 20 GB** headroom beyond current ~3 GB DB |
| Campaign isolated (`5435`) | Fixtures only — **no** 3y load; size stays small |
| VPS stage-1 (see `docs/ops/cloud-deployment-plan.md`) | **~1 TB NVMe** reference is ample for 3y contracts alone; still reserve space for WAL, dumps, and object-storage-bound PDFs **outside** PG |
| Backup target | Compressed dump often **20–40%** of on-disk DB; plan external storage for **≥ 2 full dumps + weekly** (see `vps-readiness.md`) |

### Minimum disk planning formula (contracts-focused)

```text
disk_free_required ≥
  2.2 × projected_heap(rows)
  + wal_headroom (0.2 × projected_heap)
  + one_full_dump_temp (0.4 × projected_total_db)
  + 15% filesystem margin
```

For Scenario B (~7 GB heap → ~14 GB relation, ~22 GB DB mid):

```text
≈ 2.2×7 + 1.4 + 0.4×22 + 15% ≈ 15 + 1.4 + 9 + ~4 ≈ 30 GB free minimum
  for a contracts-heavy node; 100+ GB free preferred on shared VPS.
```

---

## 7. What this campaign must **not** claim

- Final national row count or “coverage %”
- Exact GB until post-backfill measurement
- That mid-run 2.27M is the 3y universe
- That Scenario B is already loaded on `5433`

---

## 8. Post-HC measurement checklist (read-only, after writer idle)

Run **only** when PID backfill is stopped or in a quiet window; prefer **isolated restore**, not live `5433` under write:

```sql
SELECT
  relname,
  n_live_tup,
  pg_size_pretty(pg_relation_size(c.oid)) AS heap,
  pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
  pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE n.nspname = 'public' AND relname = 'pncp_supplier_contracts';

SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE relname = 'pncp_supplier_contracts'
ORDER BY pg_relation_size(indexrelid) DESC;
```

Update this document’s bands with measured numbers before VPS cutover sizing freezes.

---

## 9. References (repo)

- Checkpoint / isolation: `artifacts/campaigns/.../safety/active-process-inventory.md`
- Schema indexes: `db/current-schema.sql` (`idx_psc_*`, `idx_contracts_*`)
- Pilot volume heuristic: `scripts/crawl/run_contracts_90d_pilot.py` (module docstring)
- Window size: `scripts/crawl/contracts_crawler.py` → `CONTRACTS_WINDOW_DAYS`
- TD row citation: `docs/td-001/query-optimization.md`
- VPS disk reference: `docs/ops/cloud-deployment-plan.md` (~1 TB NVMe stage-1)
)
