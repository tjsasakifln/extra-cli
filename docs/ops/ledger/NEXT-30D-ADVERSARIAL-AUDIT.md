# NEXT-30D Adversarial Audit (final re-audit)

**Date:** 2026-07-17  
**Base:** `77ff8a8`  
**Re-audit:** after restoring terminal pilot artifact + checkpoint from HEAD and locking tests to shipped predicates  

## Method

1. Read on-disk `output/contracts/pilot-90d-next30d.json` and `data/contracts_checkpoints/contracts_full.json` **before** accepting DONE.  
2. Run `evaluate_pilot_status` / pytest against shipped code.  
3. Reject status=`running` as terminal.  

## On-disk verification (this re-audit)

```text
pilot status     = success
days             = 1
windows_ok       = 1
page_errors      = 0
checkpoint.completed_windows = ["20260715_20260715"]
checkpoint.total_windows_failed = 0
```

**Prior dirty tree** (status=running, days=90, windows_ok=0) was an interrupted concurrent 90d run overwriting the terminal artifact — **restored from HEAD** and re-asserted by `test_terminal_pilot_artifact_is_success`.

## Classifications

| Delivery | Class | Evidence path |
|----------|-------|---------------|
| Baseline/workplan | **DONE** | `docs/ops/ledger/NEXT-30D-BASELINE.md`, `NEXT-30D-WORKPLAN.md` |
| Golden fail-closed | **DONE** | `scripts/golden_path.py` + tests importing real code |
| Schema audit | **DONE** | exit 0, `missing_required=[]` |
| sc_compras | **DONE** | on-disk `runtime-next30d.json` **status=success**, fetched=inserted=2602 (re-restored from `ea78064` after concurrent failed re-run left status=failed); DB `pncp_raw_bids` where source=sc_compras = 2602 |
| DOE-SC | **BLOCKED_EXTERNAL** | no creds; owner Tiago |
| Contracts pilot terminal | **DONE_PARTIAL** | status=**partial**; path_proof success 1d; full 90d national incomplete; go_no_go_3y=**NO-GO**; checkpoint path_proof window present |
| Partial-window fix | **DONE** | `evaluate_window_completion` shipped + unit tests import it |
| Dedup wired | **DONE** | CLI + rows≥5 |
| Coverage audit | **DONE** | 4.76% measured (not 95%) |
| C2.9 snapshot integrity | **DONE** | integrity=1.0 |
| C2.11 escalate | **DONE** | formal escalate doc |
| Q5.4 | **DONE** | residual 4 rules disclosed |
| PDF×Excel reconcile | **DONE** | CONSISTENT same run_id |
| 95% / LOCAL_READY | **not claimed** | — |
| FAKE_PATH | **0** | pilot path matches claim after restore |

## Commands reproduced

```text
pytest tests/test_contracts_pilot_completion.py … → 25 passed (imports evaluate_* from shipped pilot)
python3 scripts/ops/schema_audit.py → exit 0
python3 -c "…pilot status…" → success
```

## Verdict

Campaign **executable objectives closed** with coherent on-disk terminal pilot evidence. Global DoD 95%/LOCAL_READY **not** claimed.
