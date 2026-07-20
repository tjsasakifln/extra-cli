# Session evidence — §29 rastreabilidade ledger

**Date:** 2026-07-20  
**Story:** `ROI-cand-dyn-slice-cb906bb58392`  
**Branch:** `goal/roi-rastreabilidade-cb906bb58392`  
**Agent:** @dev (Dex) — implementation only; **QA independent required before DoD flips**

## What was proven (PARTIAL §29 advance)

| # | DoD item | Proven by |
|---|----------|-----------|
| 1 | Cada execução possui erros | `record_execution` always writes `errors` list (empty on ok); unit tests + demo ledger |
| 2 | Cada relatório referencia runs de origem | `report_run_links` with `run_id` per report path; decision_pack + weekly_cycle wire `report_paths` |
| 3 | Mudanças manuais são auditáveis | `record_manual_mutation` + CLI `mutation`; fail-closed actor/path/reason |
| 4 | Overrides manuais possuem motivo | `manual_override_ledger` + `record_manual_override`; reject empty motivo |
| 5 | Overrides manuais possuem data | auto ISO timestamp or explicit `data`; validate fail-closed |
| 6 | Overrides manuais possuem autor | reject missing/blank autor (unit + CLI demo-override-reject.json) |

Optional items **NOT** claimed:

| # | Item | Status |
|---|------|--------|
| 7 | coverage reconstruct | OPEN |
| 8 | freshness reconstruct | OPEN |

## Commands (reproducible)

```bash
# Unit tests (HIGH-RISK gate)
python3 -m pytest tests/test_run_execution_ledger.py tests/test_manual_override_ledger.py -q --tb=short --no-cov
# → 19 passed (see pytest.log)

# Operator CLI demo (session root)
DEMO=docs/ops/session-2026-07-20-rastreabilidade-ledger/demo
python3 -m scripts.ops.run_execution_ledger --root "$DEMO" record \
  --command "python3 -m scripts.ops.decision_pack" --status ok \
  --report ".../decision_manifest.json" --run-id run-session-20260720-ok
python3 -m scripts.ops.run_execution_ledger --root "$DEMO" override \
  --target entity:demo-1 --action force_status \
  --motivo "fonte oficial offline" --autor tiago
python3 -m scripts.ops.run_execution_ledger --root "$DEMO" verify --out verify-invariants.json
# → ok=true, n_runs=2, missing_errors_field=[], unlinked_reports=[]
```

## Exit codes

| Step | Exit |
|------|------|
| pytest (19 tests) | 0 |
| verify_invariants (demo) | 0 (`ok: true`) |
| override missing autor | 2 (fail-closed) |
| ruff check (touched files) | 0 |

## Operational wiring (beyond unit tests)

- `scripts/ops/decision_pack.py` → `record_execution_safe` with `report_paths` + `run_id`
- `scripts/ops/weekly_cycle.py` → `record_execution_safe` with manifest/products + `cycle_id` as run_id
- **New CLI:** `python3 -m scripts.ops.run_execution_ledger {record|verify|override|mutation}`

## Artifacts in this directory

| File | Content |
|------|---------|
| `pytest.log` | 19 passed |
| `verify-invariants.json` | demo verify result |
| `sample-ledger.jsonl` | 2 execution rows (ok + failed) |
| `sample-overrides.jsonl` | 1 override with motivo/data/autor |
| `sample-mutations.jsonl` | 1 manual mutation |
| `demo-override-reject.json` | fail-closed missing autor |
| `dod-map.md` | item → evidence map |
| `proposed-dod-flips.md` | exact DoD lines for @qa to authorize |

## Explicitly NOT claimed

- Full §29 complete
- `LOCAL_READY` / `95%` / `PRE_VPS_FINAL_READY`
- VPS operational
- Coverage/freshness reconstruct (items 7–8)
- DoD.md checkbox flips (pending independent @qa)

## IDS log

| Decision | Artifact | Rationale |
|----------|----------|-----------|
| REUSE | `run_execution_ledger.record_execution` | already had errors[] + report_run_links |
| REUSE | `manual_override_ledger` | motivo/data/autor already required |
| ADAPT | `run_execution_ledger` | +CLI, +record_manual_override bridge, fail-closed mutation |
| CREATE | session evidence pack | required for QA-authorized flips |
