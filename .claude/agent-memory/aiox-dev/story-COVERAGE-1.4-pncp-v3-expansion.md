---
name: story-COVERAGE-1.4-pncp-v3-expansion
description: "COVERAGE-1.4: PNCP v3 coverage expansion — _ENGINEERING_KEYWORDS removed, modalidades expanded to 1-7, date range to 90d, delay to 0.3s"
metadata:
  type: project
---

# Story COVERAGE-1.4: PNCP v3 Coverage Expansion

**Status:** InReview (code implementation done, AC5-AC7 pending real crawl execution)

## Changes Made

### scripts/crawl/pncp_crawler_adapter.py
- **AC1:** Removed `_ENGINEERING_KEYWORDS` filter completely — deleted lines 55-60 (definition) and lines 324-329 (filter clause) plus the unused `skipped` tracking variable
- **AC2:** Changed `INGESTION_MODALIDADES` default from `"4,5,6,7,8,12"` to `"1,2,3,4,5,6,7"` (captures Pregao Presencial, Tomada de Precos, Convite)
- **AC3:** Changed `INGESTION_DATE_RANGE_DAYS` default from `30` to `90`
- **AC4:** Changed `PNCP_REQUEST_DELAY` default from `0.5` to `0.3` (300ms between requests)
- Updated `transform()` docstring to reflect no keyword filtering

### tests/test_crawler_pncp.py
- Replaced `test_transform_filters_by_keyword` with `test_transform_no_keyword_filtering`
- Removed unused imports (`hashlib`, `pytest`, `Mock`, `patch`)
- All 9 tests pass

### Existing files (not modified by this story)
- `scripts/coverage/measure_pncp_expansion.py` — already exists from previous work
- `docs/epic-coverage/pncp-expansion-report.md` — already exists from previous run

## Pending (AC5-AC7)
Real crawl execution blocked by rules. To complete:
1. `python scripts/crawl/monitor.py --source pncp --mode full`
2. `python scripts/coverage/measure_pncp_expansion.py`
3. Review `docs/epic-coverage/pncp-expansion-report.md`

## Self-Critique
Saved to `plan/self-critique-COVERAGE-1.4.json` — verdict PASSED.

## Key Risk
Changing from 6 to 7 modalidades + 30 to 90 days = ~10.5x more API calls. With 0.3s delay, 429 rate limits may spike.
