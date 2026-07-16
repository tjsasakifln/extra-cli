# DF-201: PNCP Adapter — DLQ + Watermark Integration + Client Replacement

**Epic:** DATA-FOUNDATION | **Wave:** 2 | **Story:** 4/22
**Status:** Draft
**Risk:** HIGH-RISK
**Priority:** MUST (ESSENTIAL)
**Executor:** @dev
**Quality Gate:** @architect
**Effort:** 5h

## Description

Integrate DLQ and watermark into the existing PNCP adapter (`scripts/crawl/pncp_crawler_adapter.py`). Replace the PNCP client stub at `scripts/crawl/clients/pncp/` with a real implementation inheriting from `BaseHTTPClient` (`scripts/crawl/clients/base/base.py`). Add page-level watermarks to the PNCP crawl loop. PNCP is the essential source — without fresh data, the platform is DEGRADED/FAILED. All changes backward-compatible (opt-in).

## Acceptance Criteria

1. Given PNCP crawl, watermark commits per page (page-level granularity) via `watermark_commit`
2. Given PNCP fetch failure, record routes to DLQ via `dlq_write`
3. Given `--resume`, PNCP resumes from last committed page-watermark
4. Given existing PNCP adapter, interface remains backward-compatible (new features opt-in via flags)
5. Given `scripts/crawl/clients/pncp/` stub, replaced with real `PNCPClient` inheriting from `BaseHTTPClient`

## Scope IN

- Enhance `scripts/crawl/pncp_crawler_adapter.py` with DLQ write calls on fetch/parse failures
- Add page-level watermark read/commit to PNCP crawl loop
- Replace `scripts/crawl/clients/pncp/async_client.py` stub with real implementation using `BaseHTTPClient`
- Wire `--resume` flag to read last watermark and skip already-crawled pages
- Keep all existing interfaces backward-compatible

## Scope OUT

- No changes to other source adapters
- No backfill (Wave 3)
- No PNCP data schema changes

## Dependencies

- W1: DLQ module (`scripts/crawl/dlq.py`) — dlq_write, dlq_replay
- W1: Watermark module (`scripts/crawl/watermark.py`) — watermark_commit, watermark_read
- W1: BaseHTTPClient (`scripts/crawl/clients/base/base.py`) — base client for PNCP replacement
- W1: Pipeline module (`scripts/crawl/pipeline.py`) — crawl lifecycle

## File List

- `scripts/crawl/pncp_crawler_adapter.py` — enhanced with DLQ + watermark
- `scripts/crawl/clients/pncp/__init__.py` — updated exports
- `scripts/crawl/clients/pncp/async_client.py` — replaced stub with real implementation
- `scripts/crawl/clients/pncp/circuit_breaker.py` — using shared CB from clients/pncp/
- `scripts/crawl/clients/pncp/retry.py` — using shared retry from clients/pncp/
- `tests/test_pncp_adapter.py` — new tests for DLQ + watermark integration

## Acceptance Criteria (Detailed / Given-When-Then)

- **AC1:** Given a PNCP crawl with page_size=10 and 3 pages, when crawl runs, watermark_commit is called after each page, and pipeline_watermarks has 3 entries for source='pncp'
- **AC2:** Given a PNCP fetch that raises ConnectionError, when crawl handles the error, dlq_write is called with source='pncp', error_code matches the exception, payload contains the failed request params
- **AC3:** Given a completed PNCP crawl with watermark at page=5, when --resume is used, the crawl starts from page=5 (not page=1)
- **AC4:** Given existing pncp_crawler_adapter.crawl() calls in monitor.py, after changes, the same calls work without modification (backward-compatible)
- **AC5:** Given PNCPClient().fetch(url) call, the implementation uses BaseHTTPClient.request() with proper retry/circuit-breaker from the base client

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-07-16 | Created from exec plan | Morgan (@pm) |
