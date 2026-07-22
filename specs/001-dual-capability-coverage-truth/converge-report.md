# Speckit converge — dual-capability-coverage-truth

**Date:** 2026-07-21

## Codebase vs tasks

| Task | Status | Evidence |
|------|--------|----------|
| T001–T004 Spec/ADR/errata | Done | specs/, ADR-029, ERRATA |
| T005 migration 058 | Done | db/migrations/058_dual_capability_coverage_views.sql |
| T006–T009 dual engine + CLI + unit tests | Done | dual_capability_coverage.py, test_dual_capability_coverage.py |
| T010–T012 golden path | Done | golden_path.py, test_golden_path_coverage.py |
| T013–T016 reports/claims/DOD/NEXT | Done | campaign dir |
| T017–T019 analyze/converge/quality | Done | this report + pytest |
| T020 PR/CI remote | Pending environment | commands documented |

## Remaining unbuilt work (external)

1. Merge PR + green CI on origin/main  
2. Live dual reproof acceptance pack via `register_acceptance` (no self-QA)  
3. Operational fill of coverage_evidence to raise dual % toward 95%  

No additional implementable measurement tasks without external data/ops.

## Converge verdict

**CONVERGED** for measurement spine. Operational 95% is intentionally open.
