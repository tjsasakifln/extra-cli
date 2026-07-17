# NEXT30-GATE-A — FOUNDATION_TRUTH

**Date:** 2026-07-17  
**HEAD campaign branch tip:** see `git rev-parse HEAD`  
**Verdict:** **PASS WITH CONCERNS**

| Check | Result | Evidence |
|-------|--------|----------|
| Required relations present | **PASS** | `scripts/ops/schema_audit.py` exit 0; `output/schema-audit-next30d.json` |
| Migration inventory coherent | **CONCERNS** | 54 files vs 53 rows; 12 failed rows “already exists” on non-fresh DB |
| Fresh empty-DB 54/54 re-proof this session | **NOT RE-RUN** (GATE-1 prior evidence retained) | `docs/baseline/l1-fresh-migrations.md` |
| Golden path fail-closed | **PASS** | `evaluate_run_outcome` + 9 unit tests `tests/test_golden_path_fail_closed.py` |
| Critical unit regression | **PASS** | 17 tests golden+contracts+ledger |
| Broad regression all 1575 | **NOT claimed** | Out of window justification: known pre-existing debt |

## Exit

Gate A **accepted with concerns** for campaign progress. Not equivalent to DoD `LOCAL_READY`.
