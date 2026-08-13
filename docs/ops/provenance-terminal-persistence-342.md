# Provenance terminal persistence contract (#342)

**Scope:** `pipeline_runs` terminality for the synchronous crawl adapters.  This
is a correction of the existing API, not a second provenance framework or a
change to CONFENGE feed semantics.

## Contract

- `provenance_start`, `provenance_complete`, and `provenance_fail` are
  keyword-only at the synchronous boundary.  A persistence error raises to the
  caller; there is no boolean soft-fail or synthetic fallback `run_id`.
- `source` is part of terminal run identity.  Terminal updates atomically match
  `run_id`, `source`, and `status = 'running'`.
- Unknown `run_id`, mismatched `source`, and a repeated terminal transition are
  distinct observable errors.  A run can leave `running` exactly once.
- Complete and fail persist the schema counters by their canonical names:
  fetched, deduplicated, upserted, DLQ, failed, pages planned/completed,
  watermarks committed, and duration.  Fail additionally persists the error
  message.
- PCP, DOM-SC, DOE-SC, TCE-SC, and CIGA reuse the `run_id` returned by the
  successful start write.  Failure of a terminal write is never converted to a
  successful crawler return.

## Reproducible validation

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
REQUIRE_REAL_DB=1 TEST_DSN="$LOCAL_DATALAKE_DSN" \
  python3 -m pytest tests/integration/test_provenance_terminal_persistence.py -q
python3 -m pytest tests/test_provenance.py tests/test_provenance_sync.py \
  tests/test_provenance_crawler_contract.py -q
```

The PostgreSQL test asserts stored column values, not merely that a function
was called.  Branch/PR evidence remains `VERIFIED`; DOD acceptance still
requires the exact merged `main` SHA and green canonical CI.

No ADR is added: the change stays inside the existing `ProvenanceTracker` and
its current `pipeline_runs` schema.
