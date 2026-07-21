# BASELINE — STABILIZE-GLOBAL-FULL-SUITE-01

## Pin

| Field | Value |
|-------|-------|
| Base ref | `origin/main` |
| HEAD SHA | `75e5653c4b1e338009f6e395d3ffa50066fc16dd` |
| Commit | feat(coverage): entity freshness canonical acceptance (DOD freshness item) (#65) |
| Campaign start | 2026-07-20T21:09:27-03:00 |
| Python | 3.12.3 |
| pytest | 8.4.1 |
| PostgreSQL | 16.14 via `pgvector/pgvector:pg16` container `full-suite-pg16-baseline` |
| DSN | `postgresql://test:test@127.0.0.1:5544/extra_full_suite` (disposable, not operator personal DB) |

## Migrations

- Runner: `python -m scripts.ops.apply_migrations --dsn $DSN --mode fresh` (no hard-coded max)
- Result: `migrations_ok mode=fresh applied=62 skipped=0 repaired=0`
- Max version on this main HEAD: **057** (`057_fix_upsert_opportunity_content_hash.sql`)
- Note: `058_*` exists on other branches only; not part of main HEAD migration set
- Log: `migrations-applied.log`, list: `migrations-list.txt`

## Canonical command

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5544/extra_full_suite
export DATABASE_URL=$LOCAL_DATALAKE_DSN
export CI=true
export RESILIENCE_ENV=test
export RESILIENCE_REQUIRE_DB=0   # baseline used 0; track B will set 1 for database marker path
python -m pytest tests/ \
  -m "" \
  -o addopts='' \
  --cov=scripts \
  --cov-report=term-missing \
  --cov-fail-under=10 \
  -q \
  --tb=short
```

## Results

| Metric | Count |
|--------|------:|
| PASSED | 2179 |
| FAILED | 21 |
| ERROR | 0 |
| SKIPPED | 128 |
| DESELECTED | **0** |
| Exit code | 1 |
| Duration | 816 s (≈13m31s) |
| Coverage | 32.68% (threshold 10% met) |

Full log: `logs/baseline-full-suite.log`  
JUnit: `logs/baseline-junit.xml`  
Machine manifest: `failure-manifest.json`

## Failure classification (summary)

| Class | Count | Action |
|-------|------:|--------|
| TEST_CONTRACT_STALE | 5 | Fix fixtures/tests/artifacts |
| ORDER_OR_STATE_DEPENDENCY | 16 | Isolation env + seed + conftest opt-in for real DB |
| PRODUCT_DEFECT | 0 | — |
| SCHEMA_OR_MIGRATION | 0 | Schema present; not missing migrations |
| EXTERNAL_LIVE_ALLOWED | 0 | — |
| UNKNOWN_BLOCKED | 0 | — |

## Outside original module list (incorporated)

- `tests/test_transparencia_crawler.py::TestCrawl::test_crawl_full` — blocks global suite; test contract stale vs current `crawl("full")` detect+template semantics.

## Decision (least surface)

- Prefer test/fixture/isolation fixes over production changes.
- Shared suite entry will set `REQUIRE_REAL_DB=1` + `RESILIENCE_REQUIRE_DB=1` with disposable PG16 so database/integration tests exercise real schema without operator DSN.
- No production code change until fixture-fixed contract still fails (wave 1 rule).
