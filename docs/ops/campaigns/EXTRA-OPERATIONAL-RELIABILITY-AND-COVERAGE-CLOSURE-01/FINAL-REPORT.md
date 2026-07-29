# FINAL-REPORT — EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01

**terminal_state:** `OPERATIONAL_READY_SOAK_IN_PROGRESS`  
**as_of:** 2026-07-29T15:40:00Z  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/171  

## Dual capability (joint measurement)

| capability | covered | denominator | coverage_pct | gate |
|------------|---------|-------------|--------------|------|
| open_tenders | 1093 | 1093 | **100.0%** | **PASS** |
| historical_contracts | 1093 | 1093 | **100.0%** | **PASS** |

- `dual_gate_status=PASS`
- `pipeline_success=true`
- `scope_complete=true`
- `measurement_success=true`
- same SHA / as_of / universe / policy in one invocation
- artifact: `artifacts/campaigns/.../dual-capability-coverage-summary.json`
- runner: `scripts/ops/run_dual_coverage.sh` (PYTHONPATH + venv)

## Production (VPS)

| Item | Result |
|------|--------|
| deployed campaign tip | PR #171 branch |
| contracts incremental | success (rebind attempt_run_id) |
| failed critical units after fix | 0 (ciga oneshot fixed to `-m` module) |
| timers enabled | pncp-contracts, extra-crawl-pncp, extra-crawl-ciga-ckan, extra-contracts-soak, coverage-report, health |
| soak | day 1/7 UTC `health_ok=true`; complete=false honest |

## Checkpoint / lock

- v2 logical_job_id + attempt_run_id
- shared `/run/lock/extra-contracts-writer.lock`
- weekly lake reuse by default

## Not claimed

- 7 consecutive soak days complete (epoch started; first day valid)
- FULL_OPERATIONAL_RELIABILITY_PASS before day 7

## First soak completion eligible date (UTC)

If daily observations remain healthy: **2026-08-04** (7th consecutive day from 2026-07-29).
