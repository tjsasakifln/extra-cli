# DOD accepts — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**As of:** 2026-07-23T21:15Z  
**Where:** worktree `.worktrees/dod-accept-main-hc` on `main`  
**origin/main:** `2f22fa0` (pushed)

## ACCEPTED on origin/main (sequential)

| ID | Requirement | Wave |
|----|-------------|------|
| `DOD-rol-1-definition-of-done-c2443d2b03` | Backfill cobre ≥3 anos | `fddf859` |
| `DOD-rol-1-definition-of-done-00e53389b2` | Data inicial 20230720 | `d6c311a` |
| `DOD-rol-1-definition-of-done-19ab88eea0` | Data final 20260723 | `d6c311a` |
| `DOD-rol-1-definition-of-done-c8d4fd6597` | dual historical_contracts ≥95% | `d6c311a` |
| `DOD-rol-1-definition-of-done-925c2e6bed` | Backfill integral mínimo 3y | `2f22fa0` |
| `DOD-rol-1-definition-of-done-749585a9b5` | Não reinicia janelas concluídas | `2f22fa0` |
| `DOD-definition-of-done-extra-1580defee6` | Coleta 3y no mínimo | `2f22fa0` |
| `DOD-definition-of-done-extra-d213dd4037` | Incremental pós-backfill | `2f22fa0` |

## Gates

Each: VERIFIED→ACCEPTED on branch `main`, evidence pack, green verify, CI lineage from `5f92211` run 30042874795, independent review. No force/skip.

## NOT accepted (campaign blockers)

- Off-site backup / backup externo
- Soak 7d continuous
- VPS_OPERATIONAL / PROJECT_DONE / full host reboot
- open_tenders ≥95%

## Campaign result

**BLOCKED** — `BACKUP_STORAGE_BOX_SSH` empty + soak day 1/7 only.
