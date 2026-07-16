# DF-202: PCP Client — Full DLQ/Watermark/Provenance Integration

**Epic:** DATA-FOUNDATION | **Wave:** 2 | **Story:** 5/22
**Status:** Draft
**Risk:** STANDARD
**Priority:** MUST
**Executor:** @dev
**Quality Gate:** @qa
**Effort:** 5h

## Description

Add page-level watermarks, DLQ integration, and provenance recording to the PCP crawler (`scripts/crawl/pcp_crawler.py`). PCP is a P0 production source. Use Exa MCP research to confirm real PCP API endpoints and pagination behavior.

## Acceptance Criteria

1. Given PCP crawl, watermark commits per page via `watermark_commit`
2. Given PCP fetch/parse failure, record routes to DLQ via `dlq_write`
3. Given PCP crawl start/end, provenance records created via `run_start` / `run_complete`
4. Given existing PCP pipeline, backward compatibility maintained (opt-in via flags)

## Scope IN

- Enhance `scripts/crawl/pcp_crawler.py` with DLQ write calls on failures
- Add page-level watermark read/commit to PCP crawl loop
- Add provenance run_start/run_complete recording
- Wire `--resume` flag to read last watermark
- Research PCP API endpoints via Exa MCP to confirm pagination details

## Scope OUT

- No changes to PCP data schema or transform logic
- No backfill (Wave 3)

## Dependencies

- W1: DLQ module (`scripts/crawl/dlq.py`)
- W1: Watermark module (`scripts/crawl/watermark.py`)
- W1: Provenance module (`scripts/crawl/provenance.py`)
- W1: Pipeline module (`scripts/crawl/pipeline.py`)

## File List

- `scripts/crawl/pcp_crawler.py` — enhanced with DLQ + watermark + provenance
- `tests/test_pcp_adapter.py` — new tests for DLQ/watermark integration

## Exa MCP Research Required

Before implementing, use Exa MCP to research:
- PCP API base URL and available endpoints
- Pagination parameters (page size, max pages)
- Rate limiting headers
- API status / known issues

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-07-16 | Created from exec plan | Morgan (@pm) |
