# DF-203: ComprasGov Adapter — DLQ + Watermark Integration

**Epic:** DATA-FOUNDATION | **Wave:** 2 | **Story:** 6/22
**Status:** Draft
**Risk:** STANDARD
**Priority:** MUST
**Executor:** @dev
**Quality Gate:** @architect
**Effort:** 3h

## Description

Integrate DLQ and watermark into the existing ComprasGov adapter (`scripts/crawl/compras_gov_crawler.py`). Add page-level watermarks. Ensure HTTP 429 handling with rate-limit detection + backoff (3x), then DLQ with `error_code='rate_limited'`. Circuit breaker does NOT trip on 429. HTTP 500: retry exponential backoff (base 60s, multiplier 5, max 3), then DLQ, CB tripped after threshold.

## Acceptance Criteria

1. Given ComprasGov crawl, watermark commits per page
2. Given 429 response, retry 3x with backoff, then DLQ with `error_code='rate_limited'`
3. Given 429 response, circuit breaker does NOT trip
4. Given 500 response, retry with exponential backoff (base 60s, multiplier 5, max 3), then DLQ

## Scope IN

- Enhance `scripts/crawl/compras_gov_crawler.py` with DLQ write calls
- Add page-level watermark read/commit
- Implement 429-aware retry logic (backoff, no CB trip)
- Implement 500 exponential backoff (60s base, 5x multiplier, 3 max)
- Wire `--resume` flag

## Scope OUT

- No changes to ComprasGov data schema or transform
- No backfill

## File List

- `scripts/crawl/compras_gov_crawler.py` — enhanced with DLQ + watermark + 429/500 handling
- `tests/test_comprasgov_adapter.py` — new tests for DLQ/watermark integration

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-07-16 | Created from exec plan | Morgan (@pm) |
