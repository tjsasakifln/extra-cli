# Full suite debt reduction — sc_compras obsolete skips removed

**Story:** ROI-cand-dyn-slice-5e47929809f6  
**Cycle:** cyc-2026-07-18T171940Z  
**Branch:** extra-roi/cand-dyn-slice-5e47929809f6  
**Date:** 2026-07-18  

## Change
Deleted dead skipped tests for removed HTML scraper APIs in `tests/test_sc_compras_crawler.py`:
- TestExtractTableRows, TestExtractDetailFields, TestDiagnostic, TestCheckUrl (24 skips)

## Critical readiness
```
........................................................................ [ 36%]
........................................................................ [ 73%]
.....................................................                    [100%]
197 passed, 2 deselected in 17.60s
```

## DoD recommendation
- `dod:b06848ca7f90` full suite green: **LEAVE OPEN** (critical path improved; full 2174-test suite not asserted green)

## Claims allowed
- Critical resilient-smoke path has **0 skips** from obsolete sc_compras HTML APIs
- sc_compras unit tests pass without skip debt for removed functions

## Claims forbidden
- Full suite green
- LOCAL_READY / 95% coverage
