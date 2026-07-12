---
name: story-COVERAGE-1.6-pcp-coverage-expansion-reqa
description: RE-QA PASS verdict after FAIL on first attempt — real code implementation verified for PCP page size, max pages, temporal window, UF filter
metadata:
  type: reference
---

# Story COVERAGE-1.6 PCP Coverage Expansion — RE-QA PASS

**Verdict:** PASS (after prior FAIL)
**Prior Gate:** `docs/qa/gates/coverage-16-pcp-coverage-expansion.yml`
**RE-QA Gate:** `docs/qa/gates/COVERAGE-1.6-pcp-coverage-expansion-reqa.yml`
**Date:** 2026-07-11

## Summary

First QA gate failed because `scripts/crawl/pcp_crawler.py` had zero changes (code NOT modified). After dev re-implemented with real code, RE-QA verified all ACs:

- **AC1:** `PCP_MAX_PAGES` default 200 via `PCP_MAX_PAGES_V2` env var (line 52)
- **AC2:** Temporal window 90/7 days (was 30/3) — `crawl()` line 397
- **AC3:** `while True` loop with `has_next` break + safety cap at PCP_MAX_PAGES (lines 415-456)
- **AC4:** `uf=SC` + `quantidade` in params, HTTP 400 fallback removes them and retries (lines 213-257)
- **AC5:** 305 records verified (4x vs 72 original), 201 pages processed
- **AC6/AC8:** Deferred — require PostgreSQL connectivity for entity matching and coverage measurement

## Tests & Lint

- 28/28 `test_pcp_crawler.py` passed
- 764/777 full suite (13 pre-existing unrelated failures)
- `ruff check scripts/crawl/pcp_crawler.py` — clean

## New Issue

- **PERF-001** (LOW): `_extra_params_active` resets per `_fetch_page` call. If API returned 400 for extra params, every page would waste 1 round-trip. Theoretical — API ignores unknown params without error.

## Related

- [[story-COVERAGE-1.10-pcp-diagnostic]] — diagnostic story that ran in parallel
