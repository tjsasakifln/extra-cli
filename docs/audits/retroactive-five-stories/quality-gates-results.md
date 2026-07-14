# Quality Gates Results

**Date:** 2026-07-13
**Commit:** d2ff075 (HEAD, fix: update qw-01 state for push gate [skip-ci])
**Project:** /mnt/d/extra consultoria
**Stories verified:** 1.1-1.5 (retroactive audit from commit d2ff075)

---

## 1. LINT (ruff check)

| Field | Value |
|-------|-------|
| Command | `ruff check scripts/ tests/` |
| Exit code | 1 (errors found) |
| Total errors | **2,779** |
| Fixable | 55 |
| Duration | ~30s |

### Error breakdown

| Rule | Count | Description |
|------|-------|-------------|
| S101 | 2,512 | `assert` used outside tests (mostly in test files) |
| S110 | 54 | `try-except-pass` detected, silence errors |
| Other | 213 | Various formatting/styling rules |

**Verdict: FAIL** — 2,779 lint errors, predominantly `assert` usage (S101) in test files but also `try-except-pass` (S110) and other violations across source code.

---

## 2. FORMAT (ruff format --check)

| Field | Value |
|-------|-------|
| Command | `ruff format --check scripts/ tests/` |
| Exit code | 1 (unformatted files) |
| Files to reformat | **49** |
| Files already formatted | 215 |
| Duration | ~15s |

**Verdict: FAIL** — 49 files would be reformatted, indicating inconsistent formatting across the codebase.

---

## 3. SECURITY (ruff --select S)

| Field | Value |
|-------|-------|
| Command | `ruff check --select S scripts/` |
| Exit code | 0 |
| Total security issues | **177** |
| Duration | ~10s |

### Key findings

| Issue | File | Line | Detail |
|-------|------|------|--------|
| S607 | `scripts/universe_tools.py` | 81 | Partial executable path in `subprocess.run` |
| S110 | `scripts/supabase_client.py` | 52 | `try-except-pass` swallowing ImportError |
| S110 | `scripts/validate-report-data.py` | 112 | `try-except-pass` swallowing Exception |
| S608 | `scripts/reports/coverage_gaps.py` | 58 | Possible SQL injection via string-based query construction |
| S101 | Throughout | — | `assert` statements in non-test code |

**Verdict: CONCERNS** — 177 findings, including 1 SQL injection vector (B608/Medium), bare excepts (S110), and partial path execution (S607).

---

## 4. BANDIT

| Field | Value |
|-------|-------|
| Command | `bandit -r scripts/ -ll` |
| Exit code | 0 |
| Total issues | **177** (51 Medium, 126 Low, 0 High) |
| Duration | ~20s |

### Bandit breakdown

| Severity | Count |
|----------|-------|
| High | 0 |
| Medium | 51 |
| Low | 126 |

### Notable findings

- **B608** (Possible SQL injection): e.g., `scripts/reports/coverage_gaps.py:58` — string-based SQL query construction with f-strings
- File skipped via `#nosec`: 1

**Verdict: CONCERNS** — 51 medium-severity issues, primarily hardcoded SQL expressions and potential injection vectors.

---

## 5. UNIT TESTS (pytest -v --tb=short)

| Field | Value |
|-------|-------|
| Command | `pytest tests/ -v --tb=short --timeout=60` |
| Exit code | 0 (all tests ran to completion) |
| Duration | 240s |
| **Passed** | **1,264** |
| **Failed** | **86** |
| **Errors** | 17 |
| **Skipped** | 2 |
| **Deselected** | 10 |

### Failure categories

| Category | Count | Root cause |
|----------|-------|------------|
| `test_consulting_readiness.py` | 12 | `TargetUniverse.__init__()` got unexpected keyword argument `total_resolved` — interface mismatch after refactor |
| `test_sc_compras_crawler.py` | 27 | Module no longer exports `_extract_table_rows`, `_extract_detail_fields`, `_fetch_list_page`, `_check_url` — renamed/removed API |
| `test_snapshot_reconciliation.py` | 8 | `TypeError: cannot convert dictionary update sequence element #0 to a sequence` — data format mismatch |
| `test_evidence_projection_db.py` | 9 | Assertion errors, DID NOT RAISE, database-related failures |
| `test_integration_crawl.py` | 8 | Database unavailable (connection to localhost:5433 failed — no password supplied) |
| `test_mides_bigquery_crawler.py` | 2 | Expected hash len 32, got 64 — sha256 vs md5 mismatch |
| `test_selenium_crawler_adapter.py` | 2 | Hash length mismatch (64 != 32) + missing `SeleniumBatchCrawler` |
| `test_pncp_pipeline_db.py` | 2 | Index naming diff + psql syntax error with `:'payload'` |
| `test_qw01_postgres.py` | 1 | Column `source_active` does not exist — schema drift |
| `test_transparencia_crawler.py` | 2 | Expected 79 municipios, got 80 + Timeout on full crawl |
| `test_smoke_contract_intel.py` | 1 | Cannot import `QUERY_ATIVOS_90_180` from `scripts.contract_intel.cli` |
| `test_backfill_count_covered.py` | 1 | Failed assertion |
| `test_compras_gov_crawler.py` | 3 | Failed assertions |
| `test_contract_intel_truth_v1.py` | 17 (errors) | Database unavailable |

### Error categories (17 errors)

| Category | Count |
|----------|-------|
| Database unavailable (no connection) | 11 |
| Other exceptions | 6 |

**Verdict: FAIL** — 86 failed tests + 17 errors out of 1,369 executed (93.7% pass rate excluding deselected/skipped). The majority of failures are related to database unavailability, API changes in crawlers, and hash algorithm mismatches.

---

## 6. TEST SUMMARY (pytest -q --tb=no)

| Field | Value |
|-------|-------|
| Command | `pytest tests/ --tb=no -q` |
| Duration | >120s (timed out) |
| Notes | Full run takes ~240s; results taken from the verbose run instead |

**Verdict:** Complete results captured from verbose run above.

---

## 7. MIGRATION / INTEGRATION TESTS

| Field | Value |
|-------|-------|
| Command | Included in main run as `tests/integration/` |
| Duration | ~10s combined |

### Results

| Test file | Status |
|-----------|--------|
| `tests/integration/test_all_sql_references.py` | **4 passed** |
| `tests/integration/test_migration_fresh_install.py` | **10 passed** |

**Verdict: PASS** — All 14 integration tests pass within the full test suite.

---

## 8. IMPORT CHECKS

| Module | Status | Duration |
|--------|--------|----------|
| `scripts.crawl.bids_crawler.BidsCrawler` | **OK** | ~2s |
| `scripts.matching.entity_matcher.match_entities_cascade` | **OK** | ~2s |
| `scripts.lib.universe.CanonicalUniverse` | **OK** | ~2s |
| `scripts.coverage.states.CoverageState` | **OK** | ~2s |

**Verdict: PASS** — All 4 key modules import successfully without errors.

---

## Overall Summary

| Gate | Result | Details |
|------|--------|---------|
| 1. LINT | **FAIL** | 2,779 errors, mostly S101 (assert), S110 (bare except) |
| 2. FORMAT | **FAIL** | 49 files would be reformatted |
| 3. SECURITY (ruff S) | **CONCERNS** | 177 findings; 1 SQL injection vector (B608) |
| 4. BANDIT | **CONCERNS** | 177 issues (51 medium, 126 low, 0 high) |
| 5. UNIT TESTS | **FAIL** | 86 failed, 17 errors, 1,264 passed |
| 6. TEST SUMMARY | INFO | Full verbose used instead (timeout on -q mode) |
| 7. MIGRATION TESTS | **PASS** | 14/14 passed |
| 8. IMPORT CHECKS | **PASS** | 4/4 modules import cleanly |

### Cumulative: **3 FAIL, 2 CONCERNS, 2 PASS**

### Key risks

1. **SQL injection vectors** in `scripts/reports/coverage_gaps.py` and similar string-based SQL construction
2. **Test suite degradation** — 86 failures indicate API drift between test expectations and implementation (renamed functions, changed hash algorithms, schema drift)
3. **Database dependency** — 20+ tests fail due to missing database connection; integration tests are not self-contained
4. **Format inconsistency** — 49 files out of 264 (18.5%) need reformatting
5. **Bare excepts** (`try-except-pass`) in production code swallow errors silently
