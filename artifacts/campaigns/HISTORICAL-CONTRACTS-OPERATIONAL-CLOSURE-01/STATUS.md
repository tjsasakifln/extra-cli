# Campaign STATUS — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Updated:** 2026-07-23T20:32Z  
**Result:** **BLOCKED** — see `result.json` + `UNBLOCK.md`

## Completed (evidence)

| Gate | Proof |
|------|--------|
| Spec 002 VPS/cutover | `specs/002-historical-contracts-operational-coverage/` |
| Backfill 37/37 | checkpoint + live-3y success |
| Cutover VPS | `cutover.json` count 4437142 SHA256 |
| Dual 100% PASS | `dual-coverage.json` |
| Incremental | local + VPS `pncp-contracts` success |
| Separate-DB restore | `restore.json` RTO 645s |
| PG restart recovery | `recovery.json` |
| VPS consulting package | `consulting-package-vps-meta.json` 5000/4.4M |
| main integration | PR #124 + #125 → `f25b96b` |
| Soak instrumentation | day1 freshness 22.56h; timer daily; VPS-local measure |

## Blockers (only)

1. **OFFSITE_BACKUP_CREDENTIAL** — `BACKUP_STORAGE_BOX_SSH=EMPTY` on VPS  
   → operator action in `UNBLOCK.md`
2. **SOAK_7D** — calendar day 1/7; timer armed; do not fabricate days

## Non-claims

LOCAL_READY, VPS_OPERATIONAL, PROJECT_DONE, open_tenders≥95%, full OPERATIONAL_COVERAGE_PASS.
