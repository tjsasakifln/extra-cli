# Test evidence

## Local pytest (predictive suite)

```bash
cd .worktrees/predictive-intel
export PYTHONPATH=.
python3 -m pytest tests/predictive/ -q --tb=short
# Result: 27 passed (full suite after implementation)
```

## Honesty static tests

```bash
python3 -m pytest tests/predictive/test_honesty_static.py -q
# Result: 5 passed
```

Logs: `/tmp/grok-goal-cde86c380195/implementer/honesty-tests.log`

## Migrations + immutability

```bash
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
# applied 069_predictive_intelligence.sql
```

Immutability check: `UPDATE predictive_predictions SET score=...` raises
`predictive_predictions is immutable; insert a new version instead`.

Log: `/tmp/grok-goal-cde86c380195/implementer/migrations.log`

## Dual entrypoints

```bash
python3 -m scripts.predictive claims
python3 -m scripts.workspace predictive-status --json
```

Both return claim states; commercial recommendation `PARTIAL_CLAIM_ALLOWED`.

## Production sample backtest

- Sample: 120,000 AEC-like contracts exported from `pncp_datalake` (2021–2025).
- Demand 30/60/90: BACKTEST_FAILED (BSS under 0.10).
- P2A: HISTORICAL_BACKTEST_PROVEN → SHADOW_OPERATIONAL.
- P3: DATA_BLOCKED (0 discount pairs).

See `backtest-summary.json`, `baseline-comparison.csv`, `backtest-folds.csv`.
