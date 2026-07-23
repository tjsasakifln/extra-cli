# Revalidação — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**As of:** 2026-07-23T20:50Z  
**Campaign result:** **BLOCKED** (unchanged — honest)

## SHAs

| Ref | SHA |
|-----|-----|
| `origin/main` | `5f92211` (PR #126 merge, CI run 30042874795 **success**) |
| VPS `/opt/extra-consultoria` | `5f92211` |
| Local campaign branch tip | `0d8653b` (docs: backup fail-closed proof; not yet on main) |

## VPS operational (reprobe)

| Check | Status |
|-------|--------|
| `pncp_supplier_contracts` count | **4 438 393** |
| Failed units | **0** |
| `extra-health-check.timer` | active |
| `extra-check-alerts.timer` | active |
| `extra-contracts-soak.timer` | active — next ~00:04 |
| `pncp-contracts.timer` | **enabled** — Mon/Wed/Fri 06:00; last success 2026-07-23 17:21Z (ins=1251) |
| `extra-db-backup.timer` | enabled; local dumps under `/var/lib/extra-consultoria/backups/postgresql/` |
| `BACKUP_STORAGE_BOX_SSH` | **EMPTY** (4th observation) |
| Off-site mount | none |
| Soak observations | **1/7** (2026-07-23, freshness ~22.8h, health_ok) |

## Blockers (only)

1. **OFFSITE_BACKUP_CREDENTIAL** — no Storage Box / SSH off-site credential on VPS; local dumps exist and are **not** off-site.
2. **SOAK_7D_IN_PROGRESS** — calendar day 1 only; timer armed; cannot fabricate days.

## Non-claims (still)

`LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, `open_tenders≥95%`, full `HISTORICAL_CONTRACTS_OPERATIONAL_COVERAGE_PASS`, `offsite_backup_complete`, `soak_7d_complete`.

## Claims still authorized

- `HISTORICAL_CONTRACTS_BACKFILL_37_WINDOWS`
- `HISTORICAL_CONTRACTS_DUAL_GATE_PASS` (local dual 100% PASS)
- `CUTOVER_RESTORE_OK`
- `SEPARATE_DB_RESTORE_DRILL_OK`
- `VPS_INCREMENTAL_TIMER_EXECUTED`
