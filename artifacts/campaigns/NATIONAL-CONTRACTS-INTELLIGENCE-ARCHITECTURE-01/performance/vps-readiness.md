# VPS Readiness — Backup, Restore, Migration Notes

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Subagent:** E (Performance / Ops)  
**Date:** 2026-07-22  
**Scope:** Notes for future national contracts volume — **no** production cutover claimed

---

## 1. Existing tooling (reuse, do not reinvent)

| Asset | Path | Role |
|-------|------|------|
| Backup script | `scripts/backup-database.sh` | `pg_dump --format=custom` + gzip + sshfs external store + retention |
| Restore script | `scripts/restore-database.sh` | `pg_restore` (jobs parallel), schema/data modes |
| Local proof | `scripts/ops/local_backup_restore_proof.py` | Dump → **separate** DB → table count proof (DoD §14 style) |
| Runbook | `docs/ops/backup.md` | Architecture, install, retention, FAQ |
| ADR (Reversa) | `_reversa_sdd/adrs/009-backup-automatizado-postgresql.md` | RPO ~24h, RTO <30min local |
| Systemd | `deploy/systemd/extra-db-backup.service` + `.timer` | Daily **06:00 UTC** |
| Cloud plan | `docs/ops/cloud-deployment-plan.md` | Stage-1 VPS: 32 GB RAM, ~1 TB NVMe, PG 16 |

### Local proof semantics (important)

`local_backup_restore_proof.py`:

- Requires `LOCAL_DATALAKE_DSN` / `DATABASE_URL`
- Writes `backups/local-proof/proof-*.dump` + JSON report
- Restores into **`extra_restore_proof`** (or `--restore-db`), never overwrites source
- Explicit limitation: **does not** exercise Storage Box / external path
- **Do not** run full dump of live `5433` during HC backfill (I/O contention + multi-GB dump time)

For campaign isolation, proof against **`5435`** (empty/fixture) validates **pipeline**, not national volume.

---

## 2. Dump size projection (for VPS / Storage Box)

Using storage bands from `storage-growth-estimate.md`:

| On-disk DB | Custom dump + gzip (typical 0.25–0.45×) | Temp free space during dump |
|------------|------------------------------------------|-----------------------------|
| ~3 GB (mid-run) | ~0.8–1.5 GB | ≥ 2× dump on local temp |
| ~15 GB (HC complete band) | ~4–7 GB | ≥ 15 GB free on dump host |
| ~25 GB (national 3y mid) | ~6–12 GB | ≥ 25 GB free |
| ~40 GB (stress) | ~10–18 GB | ≥ 40 GB free |

Retention (`BACKUP_RETENTION_DAILY=7`, `WEEKLY=4`) ⇒ external store capacity ≈:

```text
external ≥ (7 × daily_dump) + (4 × weekly_dump) + 20% margin
```

Example at 10 GB compressed daily ≈ **70 + 40 + 22 ≈ 130 GB** remote minimum for contracts-heavy DB alone.

---

## 3. Migration patterns (local → VPS)

### 3.1 Preferred: logical dump/restore

```bash
# Source (example — NEVER point at HC 5433 mid-write without ops approval)
export LOCAL_DATALAKE_DSN='postgresql://...@host/db'

# Backup
./scripts/backup-database.sh
# or one-shot:
# pg_dump -Fc -f national.dump "$LOCAL_DATALAKE_DSN"

# Target VPS
export LOCAL_DATALAKE_DSN='postgresql://...@vps/pncp'
./scripts/restore-database.sh /path/to/pncp_datalake-YYYY-MM-DD.dump.gz
```

| Pros | Cons |
|------|------|
| Tooling already in repo | Long wall time at 20+ GB |
| Portable across providers | Not PITR |
| Selective restore possible (`pg_restore -t`) | Indexes rebuild time on restore |

### 3.2 Acceptance proof sequence (recommended before VPS “go”)

1. Stop or quiesce writers (or use replica snapshot).  
2. `pg_dump -Fc` of national DB.  
3. `scripts/ops/local_backup_restore_proof.py` **or** restore to throwaway DB name.  
4. Compare row counts for `pncp_supplier_contracts`, critical MVs.  
5. Run smoke: migrations apply clean; one competitor + one agency query.  
6. Only then ship dump to VPS external storage and restore.

### 3.3 What **not** to do

| Anti-pattern | Why |
|--------------|-----|
| `docker cp` volume mid-backfill as “migration” | inconsistent files, no proof |
| Restore **over** live HC database | destroys parallel campaign |
| First restore ever = production cutover | no RTO evidence |
| Claim VPS_OPERATIONAL without 7-day stability | violates DoD / Reversa target-scope honesty |
| Store PDFs inside PG then migrate as “data lake” | cloud plan forbids; use object storage |

---

## 4. VPS resource readiness vs national 3y

| Resource | Stage-1 plan | National contracts fit |
|----------|--------------|------------------------|
| Disk ~1 TB NVMe | plan | **Yes** for DB + dumps + OS if contracts ≲ 50 GB and PDFs external |
| RAM 32 GB | plan | **Yes** for PG shared_buffers ~8 GB + crawlers; tune after load |
| CPU dedicated | plan | Needed for concurrent crawl + nightly mart refresh |
| Backup timer 06:00 UTC | existing | Keep **before** heavy crawl windows (ADR-009 timing) |
| WAL / PITR | future (pgBackRest / WAL-G) | Not required for first national load; plan evolution when RPO < 24h needed |

### shared_buffers / work_mem (guidance only)

At 6–10M contract rows:

| Setting | Starting hint |
|---------|----------------|
| `shared_buffers` | 25% RAM on dedicated PG box (e.g. 8 GB of 32) |
| `effective_cache_size` | ~50–75% RAM |
| `work_mem` | 32–64 MB (watch parallel hashagg explosions) |
| `maintenance_work_mem` | 1–2 GB for index builds / vacuum |
| `max_parallel_workers_per_gather` | 2–4 on 4+ cores |

**Do not** retune live HC Docker without ops ownership.

---

## 5. Timer / crawl coexistence on VPS

Existing units include `extra-db-backup.timer`, `pncp-contracts.timer`, `pncp-crawl-*.timer`, health/metrics.

| Rule | Rationale |
|------|-----------|
| Backup window free of full national contracts crawl | dump consistency + I/O |
| Index builds (`CONCURRENTLY`) not overlapping backup | double I/O |
| Mart refresh after incremental crawl, not during | fresher + cheaper |
| Alerts on backup failure (`BACKUP_NOTIFY_CMD`, `extra-check-alerts`) | RPO honesty |

---

## 6. Campaign-specific isolation

| DB | Port | Backup/migrate role now |
|----|------|-------------------------|
| `extra_test` | 5433 | **Protected** — HC writer; no campaign dumps unless ops + idle |
| `extra_national_intelligence_test` | 5435 | Fixture schema only; optional **tiny** proof of backup scripts |
| Future VPS `pncp` | 5432 | Production target after gates |

Env preference for this campaign: `NATIONAL_INTEL_DSN` → 5435 only.

---

## 7. Readiness checklist (honest)

| Item | Status |
|------|--------|
| Backup scripts exist | **Yes** |
| Restore scripts exist | **Yes** |
| Local proof harness exists | **Yes** |
| External storage path proven for **national-sized** dump | **Not claimed** |
| HC 3y complete + measured sizes | **In progress** (parallel campaign) |
| VPS_OPERATIONAL / LOCAL_READY | **Non-claims** per STATUS.md |
| This architecture campaign migrated national data | **No** — design only |

---

## 8. References

- `scripts/backup-database.sh`, `scripts/restore-database.sh`  
- `scripts/ops/local_backup_restore_proof.py`  
- `docs/ops/backup.md`, `docs/ops/cloud-deployment-plan.md`  
- `deploy/systemd/extra-db-backup.timer`  
- `./storage-growth-estimate.md`, `./operational-limits.md`
)
