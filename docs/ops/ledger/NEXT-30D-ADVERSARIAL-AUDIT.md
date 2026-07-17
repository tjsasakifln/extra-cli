# NEXT-30D Adversarial Audit (final)

**Date:** 2026-07-17  
**Base:** `77ff8a8`  
**Method:** confront claims vs SQL, JSON runtimes, pytest, git log  

## Classifications

| Delivery | Class | Evidence path |
|----------|-------|---------------|
| Baseline/workplan | **DONE** | `docs/ops/ledger/NEXT-30D-BASELINE.md`, `NEXT-30D-WORKPLAN.md` |
| Golden fail-closed | **DONE** | `scripts/golden_path.py` + 9 tests |
| Schema audit | **DONE** | exit 0, `missing_required=[]` |
| sc_compras | **DONE** | `output/sc_compras/runtime-next30d.json` fetched=2602 |
| DOE-SC | **BLOCKED_EXTERNAL** | no creds; owner Tiago |
| Contracts pilot terminal | **DONE** | `output/contracts/pilot-90d-next30d.json` status=success |
| Partial-window fix | **DONE** | crawler + tests |
| Dedup wired | **DONE** | CLI + rows≥5 |
| Coverage audit | **DONE** | 4.76% measured (not 95%) |
| C2.9 snapshot integrity | **DONE** | integrity=1.0 |
| C2.11 escalate | **DONE** | formal escalate doc |
| Q5.4 | **DONE** | residual 4 rules disclosed |
| PDF×Excel reconcile | **DONE** | CONSISTENT same run_id |
| Org ranking A | **DONE** | contracts semantic |
| 95% / LOCAL_READY | **FAILED if claimed** | **not claimed** |
| FAKE_PATH | **0** | — |

## Commands reproduced

```text
pytest tests/test_golden_path_fail_closed.py tests/test_contracts_* tests/test_golden_path_ledger.py -q --no-cov  → 20 passed
python3 scripts/ops/schema_audit.py → exit 0
SELECT count(*) FROM pncp_supplier_contracts → 31219
pilot-90d-next30d.json status=success windows_ok=1 page_errors=0
```

## Verdict

Campaign **executable objectives closed**. Global DoD 95%/LOCAL_READY **not** met and **not** claimed.
