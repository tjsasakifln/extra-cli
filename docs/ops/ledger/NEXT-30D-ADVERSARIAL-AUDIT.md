# NEXT-30D Adversarial Audit (independent)

**Auditor role:** A10 — does not implement the audited fronts  
**Date:** 2026-07-17  
**Branch:** `epic/next-30d-multiagent-execution`  
**Base SHA:** `77ff8a8`  

## Method

1. Confront claims with files, SQL counts, pytest exits, JSON runtimes.  
2. Reject `[x]` without evidence.  
3. Classify: DONE | DONE_PARTIAL | BLOCKED_EXTERNAL | FAILED | FAKE_PATH.

## Scorecard

| Delivery | Claim | Audit | Notes |
|----------|-------|-------|-------|
| Baseline + workplan | exists | **DONE** | `NEXT-30D-BASELINE.md`, `NEXT-30D-WORKPLAN.md` |
| Golden fail-closed | strict default | **DONE** | unit tests 9/9; code `evaluate_run_outcome` |
| Schema audit | exit 0 | **DONE_PARTIAL** | relations OK; migration row debt remains |
| sc_compras ingest | 2602 | **DONE** | runtime JSON substantiated |
| DOE-SC | — | **BLOCKED_EXTERNAL** | no credentials |
| Contracts 90d | multi-k rows | **DONE_PARTIAL** | data flowing; pilot JSON not closed at audit time |
| Partial window fix | code | **DONE** | unit tests + crawler change |
| Dedup wired | CLI + rows | **DONE** | synthetic multi-source proof; production multi-source still thin |
| Coverage audit | measured | **DONE_PARTIAL** | ~4.76% editais crude; not 95% |
| Q5.4 remediation | ruff 44→4 | **DONE_PARTIAL** | residual 4 rules; mypy debt remains |
| CI critical tests | expanded | **DONE** | see q5.4-remediation + ci.yml |
| Org ranking A | contracts | **DONE** | real ranking JSON |
| PDF/Excel reconcile | tool | **DONE_PARTIAL** | tools present; full same-run pair not universal |
| C2.11 remediação 95% | — | **FAILED / NOT_STARTED** | out of remaining capacity |
| LOCAL_READY | — | **FAKE if claimed** | **must not claim** |

## Fake-green hunt

| Risk | Result |
|------|--------|
| Success with empty essential sources | Mitigated by strict mode + tests |
| Window partial as complete | Mitigated in contracts_crawler |
| Coverage % from monitor as DoD | Documented as data_presence only |
| Dedup “production” from fixtures only | Labeled synthetic |
| Q5.4 “all green” | Residual 4 ruff + mypy debt disclosed |

## Commands reproduced (sample)

```bash
PYTHONPATH=. python3 -m pytest tests/test_golden_path_fail_closed.py -q --no-cov  # 9 passed
PYTHONPATH=. python3 scripts/ops/schema_audit.py  # exit 0
# sc_compras runtime JSON present with fetched=2602
# SELECT count(*) FROM pncp_supplier_contracts → thousands mid-pilot
# SELECT count(*) FROM dedup_cross_source → ≥3
```

## Verdict

**Campaign has real execution value.** Not full 30-day CP close. Accept as **substantial NEXT-30D advance** with honest PARTIAL/BLOCKED flags. Reject any claim of 95% or LOCAL_READY.
