# Plan — Spec 005 Stratified Recall Source Resilience

## Architecture

```
independent_inventory (public APIs only)
        │ freezes
        ▼
 gold-sample.json + sample-lock.json (denominator_hash)
        │
        ├─► evaluate (labels required) ──► PARTIAL/NOT_READY/FAIL/PASS + gate_exit
        │
        └─► capture_window (isolated DSN) ──► opportunity_intel
                    │
                    ▼
              auto-match (fail-closed) ──► labeled gold ──► evaluate
```

## Modules

| Module | Role |
|--------|------|
| `scripts/coverage/recall_benchmark.py` | Pure evaluate + lock + gate CLI |
| `scripts/coverage/independent_inventory.py` | Gold collection (no ops tables) |
| `scripts/coverage/recall_capture_window.py` | Isolated capture/replay upsert |
| `scripts/ops/campaign_stratified_recall_*.py` | Gate / verify / RC |
| `tests/unit/coverage/test_recall_benchmark_adversarial.py` | Fail-closed attacks |

## Thresholds (normative)

- `MIN_UNIQUE_ITEMS = 50`
- `MIN_PER_STRATUM = 5`
- `GLOBAL_TARGET_PCT = 95.0`
- `STRATUM_FLOOR_PCT = 90.0` for every required stratum

## Isolation

- Worktree `/tmp/extra-cli-recall-source-01`
- Postgres `127.0.0.1:5437/extra_recall_rc`
- Never ssh ec-prod / prod DSN / soak paths

## Phases

1. Harden evaluator + tests  
2. Freeze sample plan + collect gold  
3. First fail-closed benchmark  
4. Capture + match + replay  
5. Artifacts + gates + RC  
6. Independent review findings  

## Risks

- Portal rate limits (429) → external_unavailable / BLOCKED not sample shrink  
- Thin nature strata (câmara/autarquia) need multi-page PNCP search  
- Parallel campaigns: own adapters via file-ownership lease  
