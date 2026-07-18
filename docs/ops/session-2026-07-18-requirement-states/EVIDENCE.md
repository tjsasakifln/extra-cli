# Evidence — ROI-cand-dyn-slice-b8d41f43fbfc

**Cycle:** `cyc-2026-07-18T172517Z`  
**Candidate:** `cand-dyn-slice:b8d41f43fbfc`  
**Section:** Estados, aplicabilidade e bloqueio  
**HEAD at implementation:** post-recovery epic tip  

## Commands

```bash
python3 -m scripts.ops.requirement_states seed \
  --out docs/ops/session-2026-07-18-requirement-states/reconstruct.json
python3 -m scripts.ops.requirement_states reconstruct \
  --out docs/ops/session-2026-07-18-requirement-states/reconstruct-after.json
python3 -m pytest tests/test_requirement_states.py tests/test_dod_process_integrity.py -q --tb=short
```

## Results

- pytest: **12 passed** (8 new + 4 process integrity)
- reconstruct: `ok: true`, ledger_records=5
- policy flags all true (unchecked non-accepted, PARTIAL≠DONE, BLOCKED visible, NA justified, absence≠0, gates DONE+NA only, reconstructable)

## Artifacts

- `scripts/ops/requirement_states.py`
- `tests/test_requirement_states.py`
- `data/requirement_states/ledger.json`
- `docs/ops/session-2026-07-18-requirement-states/reconstruct.json`

## DoD flips authorized (9 items in section, 8 newly flipped; 1 pre-existing)

See DOD.md «Estados, aplicabilidade e bloqueio».

## Forbidden claims still hold

- LOCAL_READY / PRE_VPS_FINAL_READY / VPS_OPERATIONAL / PROJECT_DONE not claimed
- No NA used to inflate campaign meta (NA example is out-of-scope multi-tenant, not open commercial promise)
