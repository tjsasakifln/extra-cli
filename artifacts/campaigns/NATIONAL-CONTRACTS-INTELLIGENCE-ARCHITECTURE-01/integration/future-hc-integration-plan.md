# Integration plan — future merge with HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Status:** READY_FOR_INTEGRATION (architecture side)  
**Do not execute while HC live backfill writes `extra_test:5433`.**

## Preconditions (HC campaign)

1. All planned 3y windows complete (or residual gaps documented).
2. Entity evidence projection written with `window_complete` only when true.
3. Dual `historical_contracts` measured with real evidence; gate status honest.
4. Checkpoint `hc_closure_3y` stable; no active writer PID.

## Preconditions (this campaign)

1. Branch rebased onto accepted `main` that includes HC merges.
2. Migration 059 applied in target env **after** HC schema baseline.
3. `NATIONAL_INTEL_DSN` may then point read-only at production datalake **or** a restore copy — never share writer connection with crawlers.

## Steps

1. `git fetch origin && git rebase origin/main` on campaign worktree only.
2. Resolve conflicts consciously (prefer dual coverage from main; keep `scripts/national_intel` and 059).
3. Apply migrations on staging DB restore (not live writer).
4. Smoke: `python -m scripts.national_intel competitors --limit 20` against restore.
5. Re-run `pytest tests/national_intel/ --no-cov`.
6. Optional draft PR; **no** auto-merge; **no** force-push.
7. Do **not** mark DOD coverage from intelligence products.

## Non-steps

- No `--reset-checkpoint` on HC paths.
- No copy of HC checkpoint semantics into intel layer.
- No dual coverage threshold changes.
