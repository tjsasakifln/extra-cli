# PR #187 Performance Report

## Chunked extraction (structural + synthetic scale)

### Implementation
- `scripts/pseo/chunked_extract.py` — `fetch_chunked` / `iter_fetch_chunked` / `reduce_rows_chunked`
- `pipeline.load_from_db` uses named server-side cursors + `fetchmany` only (no `fetchall` on large tables)
- Isolation: REPEATABLE READ, read-only, `statement_timeout`, `application_name=extra-pseo-export`

### Synthetic benchmark (≥250k rows) — **executed**

Command path: `benchmark_synthetic_extraction(250_000, chunk_size=5000)`  
Test: `tests/pseo/test_chunked_scale.py::test_synthetic_250k_chunked_benchmark_deterministic`  
Evidence: `logs/pseo-250k-benchmark.json`

| Metric | Value |
|--------|-------|
| rows | **250_000** |
| batches | **50** (chunk 5000) |
| fetchmany calls | **51** (includes terminal empty) |
| fetchall calls | **0** |
| elapsed | **0.3785 s** |
| RSS start | 59.64 MiB |
| RSS peak | 65.76 MiB |
| RSS delta | **6.12 MiB** |
| deterministic | second run same `sum_valor` / `by_uf` |

### Fixture export
- 40 contracts + 200 bids — full pipeline + validate ~seconds (suite 53 tests in ~7s)

## Non-claims
- Not claiming measured production Postgres 250k+ with real DSN in this campaign.
- Structural path is proven; synthetic scale proves fetchmany-only + bounded aggregate memory.
