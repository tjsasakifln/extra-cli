# Converge report — Spec 002

**Date**: 2026-07-23  
**Campaign**: HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

## Purpose

Compare Spec 002 intent vs code, runtime, handoff, and DOD; list remaining unbuilt work as tasks.

## What is implemented (repo)

| Area | Evidence |
|------|----------|
| Applicability policy 2.1 + tests | commits on branch |
| Entity evidence adapter + mig 059 | scripts/coverage/contracts_entity_evidence.py |
| Proof-gated success_zero | load_checkpoint_window_proof + adversarial tests |
| 90d pilot GO + 3y runner | run_contracts_90d_pilot |
| Incremental command | run_contracts_incremental |
| Weekly contracts fail-closed | weekly_cycle compute_exit_code + tests |
| Export/restore fail-closed | scripts/ops/export_*.sh restore_*.sh |
| systemd unit fixes + validator | deploy/systemd/*, validate_systemd.py |
| prometheus_client dependency | requirements.txt |

## What is running (ops)

| Area | State |
|------|-------|
| Local backfill writer PID | Alive; ~28/37 windows |
| Local contracts rows | ~3.55M (volume ≠ coverage) |
| VPS contracts snapshot | 3 337 776; ckpt 26/37; timers PNCP off |
| Dual historical_contracts | FAIL 0% pre-projection |
| Host failed units | 7 (pre-unit-apply) |

## Remaining work (must complete for PASS)

1. Finish 37/37 windows (or cutover mid-flight then finish on VPS only)
2. Final export+restore with hash/count gates
3. Apply systemd on host; clear failed units
4. Project evidence with final checkpoint proof
5. Dual ≥95% or nominal gaps + source proof
6. Incremental + freshness on VPS
7. Consulting package real from VPS
8. Off-site backup + separate restore
9. Reboot/failure drills
10. Soak 7d
11. CI green + review + merge + sequential DOD

## Spec deltas applied this converge

- VPS cutover moved from non-goal → in scope
- Host of record Netcup Debian 13 / PG 17
- success_zero proof chain mandatory
- Traceability table with OPEN/IMPLEMENTED states
- tasks.md honest checkboxes

## Non-claims preserved

No LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE / open_tenders 95%.
