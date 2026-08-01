# PR #187 Performance Report

## Chunked extraction (structural + synthetic scale)

### Implementation
- `scripts/pseo/chunked_extract.py` — `fetch_chunked` / `iter_fetch_chunked` / `reduce_rows_chunked`
- `pipeline.load_from_db` uses named server-side cursors + `fetchmany` only (no `fetchall` on large tables)
- **B3:** classified contracts + AEC bids spill to **temp SQLite staging** (`scripts/pseo/staging.py`);
  raw batches discarded; no giant `pre_classified` list returned from extract; staging securely deleted after export
- Isolation: REPEATABLE READ, read-only, `statement_timeout`, `application_name=extra-pseo-export`
- Failure does not promote snapshot (atomic write + staging wipe)

### Synthetic benchmark (≥250k rows, extract path) — **executed**

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

### E2E export path (B4)

Test: `tests/pseo/test_benchmark_e2e.py`
- **CI:** 5k contracts / 2k bids via `stage_from_rows` → `build_export` → `write_export` (same path as `export_web_cfg`)
- **Full:** 250k / 100k behind `PSEO_BENCH_FULL=1` (skipped by default)
- Measures: duration, RSS start/peak/delta, files, validation, dataset_hash, determinism (2 runs), CANDIDATE default

### Fixture export
- 40 contracts + 200 bids — full pipeline + validate; suite `tests/pseo/` green

## Non-claims
- Not claiming measured production Postgres 250k+ with real DSN in this campaign.
- Structural path is proven; synthetic scale proves fetchmany-only + SQLite staging + bounded aggregate memory.
- E2E CI bench ≠ production DSN scale.
