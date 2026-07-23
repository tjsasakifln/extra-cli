# Campaign STATUS — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Updated:** 2026-07-23T20:51Z  
**Result:** **BLOCKED** — see `result.json` + `UNBLOCK.md`  
**Revalidation:** `revalidation-2026-07-23T20.md`

## Completed (evidence)

| Gate | Proof |
|------|--------|
| Spec 002 VPS/cutover | `specs/002-historical-contracts-operational-coverage/` |
| Backfill 37/37 | checkpoint + live-3y success (span ≥3.01y) |
| Cutover VPS | `cutover.json` + VPS count **4438393** |
| Dual 100% PASS | `dual-coverage.json` |
| Incremental | local + VPS `pncp-contracts` success; timer **enabled** Mon/Wed/Fri |
| Separate-DB restore | `restore.json` RTO 645s |
| PG restart recovery | `recovery.json` |
| VPS consulting package | `consulting-package-vps-meta.json` 5000/4.4M |
| main integration | PR #124 + #125 + #126 → **`5f92211`** (CI green) |
| VPS head | **`5f92211`** |
| Soak instrumentation | day1 freshness ~22.8h; timer daily; measure_mode local_vps + ssh |
| DOD map | `dod-id-map.md` / `dod-id-map.json` |
| DOD first item | `DOD-rol-1-definition-of-done-c2443d2b03` **VERIFIED** (accept blocked: not on main) |

## Blockers (only)

1. ~~**OFFSITE_BACKUP_CREDENTIAL**~~ — **RESOLVED 2026-07-23**  
   Netcup Storagespace NFS ordered + mounted; dump 403 MiB + sha256 on `/mnt/storage-box`  
   → `storagespace-provisioned.md` · `backup-offsite.json` status **ok**
2. **SOAK_7D** — calendar day 1/7; timer armed; do not fabricate days

## Non-claims

LOCAL_READY, VPS_OPERATIONAL, PROJECT_DONE, open_tenders≥95%, full OPERATIONAL_COVERAGE_PASS.

## DOD accepts (main worktree, not pushed)

See  — 4 items ACCEPTED on local main (, ). Campaign **result remains BLOCKED** (offsite + soak).

## DOD accepts on origin/main (2026-07-23T21:15Z)

**8 items ACCEPTED** and pushed (`2f22fa0`). See `dod-accepts.md`.

Campaign **result remains BLOCKED** (offsite credential + soak day 1/7).

## Session close 2026-07-23T22:30Z

- Backfill **UP** on VPS (4 438 393 rows, checkpoint 37/37).
- Off-site NFS **ok**.
- Campaign **BLOCKED** only on soak 7d.
- Full handoff: `HANDOFF.md`
