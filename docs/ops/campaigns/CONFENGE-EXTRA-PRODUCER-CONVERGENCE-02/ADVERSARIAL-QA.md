# ADVERSARIAL-QA

Module suites `tests/bofu_evidence` + `tests/national_coverage` +
`tests/public_integrity`: **104 passed, twice** (`module-tests-1.txt`,
`module-tests-2.txt`). `REQUIRE_REAL_DB=1` so persist `real_db` ran.

## National coverage

- extra_1093 as official_source refused
- 100% SC closed still `national_claim_authorized=false`
- BLOCKED official → `coverage_pct=null`
- unconsulted partition is BLOCKED, never ZERO_CONFIRMED
- >50k in-memory corpus refused (existing corpus test)
- stale last_seen downgrades authorization (`stale_universe`)
- content_hash replay match
- consumer view `is_insertable_into=NO`; extra_1093 INSERT refused

## BOFU

- versioned #437 evaluate payload accepted; slim fixture refused as live
- #435 handoff schema accepted; `catalog_mode=fixture` refused as live
- eight families; `expires_at` == `expires`
- publication/index/national false
- comparables only on `orcamento_bdi`
- BLOCKED coverage keeps national false
- frozen dual run hashes match; wall-clock → HOLD not READY
- CLI without `--synthetic-fixture` or versioned paths refuses

## Public integrity

- invalid CNPJ, multi-page, dupes, occurrence, complete empty,
  timeout, 429, 5xx, schema drift, parse incomplete, degraded source,
  stale cache, clock skew, unstable order, replay, CNPJ-in-log,
  forbidden copy
- failure fixtures never `NO_MATCH_CONFIRMED`
- live-safe canary without API key: aggregate `UNKNOWN` (not
  `NO_MATCH_CONFIRMED`); no CNPJ in stdout/stderr

## Policy

- ruff check scripts/tests: PASS
- generated-artifacts-policy vs origin/main: PASS (BOFU pack dumps omitted)
- PR reviewability `--draft`: PASS
- pytest skip policy: PASS
- bandit module not installed in the local venv; CI job remains the required check
- mypy CI job does not type-check these producer trees (same as source PRs)

No addopts/coverage/skip-policy reductions.
