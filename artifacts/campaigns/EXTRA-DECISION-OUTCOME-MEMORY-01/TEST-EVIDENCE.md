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


## Full suite (local)

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
export REQUIRE_REAL_DB=1
python3 -m pytest tests/ -q --tb=line --no-cov
```

Result: **3537 passed**, 122 skipped, 11 deselected, **2 failed** (not in campaign radius):

1. `tests/test_golden_path_coverage.py::test_coverage_live_clean_db` — local open_tenders data state `presence_not_measurable:fully_unmapped` (environment/data, not decision_memory code).
2. `tests/test_resilience_vertical_slice.py::test_vertical_slice_postgres_real_path` — transient on first run; **re-run PASS**.

Targeted decision_memory + code org gate: **41 passed**.

`test_critical_path_no_except_pass`: PASS after removing except-pass in review adapter.
