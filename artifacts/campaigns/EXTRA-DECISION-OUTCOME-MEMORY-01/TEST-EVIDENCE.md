# Test evidence

Command:

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/decision_memory/ tests/test_extra_decision_loop.py -q --tb=line --no-cov
```

Result: **40 passed** (real PostgreSQL; autouse psycopg2 mock bypassed for `decision_memory` path).

Coverage areas:

- models/mapping/identity/temporal/idempotency (unit)
- append-only, supersession, concurrency, isolation (PG)
- import dry-run/apply/idempotent
- weekly-board, metrics denominators, forbidden causality
- CLI smoke entry points
- review canonical + artifact-only + DB fail-closed
- scale smoke 120 decisions

Ruff (ignore UP042): All checks passed  
mypy scripts/decision_memory: Success
