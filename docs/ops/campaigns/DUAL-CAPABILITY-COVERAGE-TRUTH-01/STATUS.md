# STATUS — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Status:** MEASUREMENT_SPINE_COMPLETE (awaiting merge/CI + ops fill)  
**Date:** 2026-07-21

## Delivered

* Spec Kit feature `001-dual-capability-coverage-truth` (spec/plan/tasks/analyze/converge)
* ADR-030 single spine
* `scripts/coverage/dual_capability_coverage.py` + CLI
* golden_path dual integration (`--execute-dual-coverage-only`, dual `--execute-coverage-only`)
* migration `058_dual_capability_coverage_views.sql`
* unit tests (21) proving no any_row / no average / dual independence
* ERRATA for 214/1093=19.5791%
* NEXT-DOD-PATH.md
* DOD honest PARTIAL dual measurement annotations

## Live reproof (extra_test)

| Capability | Aplicáveis | Cobertos | Coverage | Gate 95% | Fresh | Stale | Unknown | Blocked |
|------------|------------|----------|----------|----------|-------|-------|---------|---------|
| open_tenders | 1093 | 0 | 0.0% | FAIL | 0 | 0 | 0 | 0 |
| historical_contracts | 1093 | 0 | 0.0% | FAIL | 0 | 0 | 0 | 0 |

measurement_success=true · coverage_gate_pass=false


## Exit semantics (post-skeptic fix)

- dual-only: measurement_ok + gate_fail → overall=`coverage_gate_failed`, exit **2**
- measurement_fail → overall=`failed`, exit **1**
- both gates pass → overall=`success`, exit **0**
- full strict path: evaluate_run_outcome honors coverage_gate_pass
