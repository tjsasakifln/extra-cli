# Active Process Inventory — PARALLEL ISOLATION

**Campaign:** `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Inspected at:** 2026-07-22T22:15:00Z (approx)  
**Inspector worktree:** `/mnt/d/extra-consultoria-national-intelligence`  
**Inspection mode:** read-only against host processes; no kill/restart

## 1. Protected parallel campaign

| Field | Value |
|-------|--------|
| Campaign ID | `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01` |
| Main worktree | `/mnt/d/extra consultoria` |
| Branch | `campaign/historical-contracts-operational-closure-01` |
| HEAD (active tree) | `d49b103` (ahead of `origin/main`) |
| Status | **LIVE 3y backfill RUNNING** |

## 2. Live backfill process (DO NOT TOUCH)

| Field | Value |
|-------|--------|
| PID | `27115` |
| Elapsed (at inspection) | ~6h |
| Command | `python3 -m scripts.crawl.run_contracts_90d_pilot --dsn postgresql://test:***@127.0.0.1:5433/extra_test --days 1098 --reset-checkpoint --checkpoint-dir data/contracts_checkpoints/hc_closure_3y --output-json artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/live-3y.json` |
| Note on flags | Process already started with `--reset-checkpoint` historically; **this campaign must never re-issue reset** or interrupt PID |
| Auto-resume supervisor | Separate bash loop waits on PID 27115 and will resume **without** `--reset-checkpoint` |

## 3. Checkpoint state (read-only snapshot)

Path: `data/contracts_checkpoints/hc_closure_3y/contracts_full.json` (in active campaign tree)

| Metric | Value |
|--------|--------|
| completed_windows | 19 |
| total_contracts_fetched | 1,517,280 |
| total_windows_failed | 4 |
| current_window_start | 20250609 |
| updated_at | 2026-07-22T21:52:35Z |
| last_error (sample) | PNCP HTTP 400 on page 186 |

## 4. Database used by active backfill

| Field | Value |
|-------|--------|
| Host/port | `127.0.0.1:5433` |
| Database | `extra_test` |
| Container | `extraconsultoria-test-db-1` (healthy, 8h+) |
| Postgres session | `postgres: test extra_test 172.21.0.1 idle` (linked to crawler) |
| Table of interest | `pncp_supplier_contracts` ~2.27M live rows, ~2.5 GB |
| Full DB size | ~2.6 GB |

**This campaign MUST NOT write to `extra_test` on 5433.**

## 5. Other relevant containers (leave running)

| Name | Ports | Role | Action |
|------|-------|------|--------|
| extraconsultoria-test-db-1 | 5433→5432 | Active backfill DB | **DO NOT restart** |
| smartlic-datalake | 54399→5432 | SmartLic (separate product) | ignore |
| recuperador-* / evolution_* / n8n | various | Other products | ignore |

## 6. This campaign resources (isolated)

| Resource | Value |
|----------|--------|
| Worktree | `/mnt/d/extra-consultoria-national-intelligence` |
| Branch | `campaign/national-contracts-intelligence-architecture-01` |
| Base SHA | `a38981bfa616b8f47363da6ff91b12a28bec218c` (`origin/main`) |
| Isolated DB container | `extra-national-intel-db` |
| Isolated port | **5435** |
| Isolated database | `extra_national_intelligence_test` |
| Isolated DSN (masked) | `postgresql://test:***@127.0.0.1:5435/extra_national_intelligence_test` |

## 7. Process risk assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Shared host CPU/IO with backfill | MEDIUM | Prefer fixture-driven tests; avoid heavy scans on 5433 |
| Accidental write to 5433 | HIGH if misconfigured | Default DSN env = 5435 only in this worktree |
| Checkpoint mutation | CRITICAL if touched | Never open `hc_closure_3y` for write |
| git ops on active worktree | CRITICAL | Never checkout/reset/stash there |

## 8. Claims from this inventory

- Backfill is **running** and must remain untouched.
- National volume in `extra_test` is **ingestion progress**, not SC coverage proof.
- This campaign has **independent** worktree, branch, DB name, and port.
