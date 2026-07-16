# DF-204: Remaining Sources — CIGA CKAN + TCE-SC + DOE-SC + DOM-SC Provenance + Watermarks

**Epic:** DATA-FOUNDATION | **Wave:** 2 | **Story:** 7/22
**Status:** Draft
**Risk:** STANDARD
**Priority:** SHOULD
**Executor:** @dev
**Quality Gate:** @qa
**Effort:** 4h

## Description

Add provenance recording and fine-grained watermarks to existing crawlers: CIGA CKAN (`scripts/crawl/ciga_ckan_crawler.py`, coverage-only, DLQ optional per spec), TCE-SC (`scripts/crawl/tce_sc_crawler.py`), DOE-SC (`scripts/crawl/doe_sc_crawler.py`), DOM-SC (`scripts/crawl/dom_sc_crawler.py`). These are existing crawlers needing DLQ + watermark + provenance enhancement.

## Acceptance Criteria

1. Given TCE-SC crawl, provenance record created on start/end (`run_start`/`run_complete`)
2. Given DOE-SC crawl, watermark committed per date
3. Given DOM-SC crawl, watermark committed per date
4. Given CIGA CKAN crawl, provenance record created
5. Given any crawl failure, error routes to DLQ for TCE/DOE/DOM (CIGA CKAN is DLQ-optional)

## Scope IN

- Add watermark + provenance to `tce_sc_crawler.py`
- Add watermark + provenance to `doe_sc_crawler.py`
- Add watermark + provenance to `dom_sc_crawler.py`
- Add provenance to `ciga_ckan_crawler.py` (DLQ optional)
- Wire `--resume` flag for source-specific resume

## Scope OUT

- No changes to data schemas or transforms
- No backfill

## File List

- `scripts/crawl/tce_sc_crawler.py` — enhanced with DLQ + watermark + provenance
- `scripts/crawl/doe_sc_crawler.py` — enhanced with DLQ + watermark + provenance
- `scripts/crawl/dom_sc_crawler.py` — enhanced with DLQ + watermark + provenance
- `scripts/crawl/ciga_ckan_crawler.py` — enhanced with provenance
- `tests/test_remaining_sources_adapter.py` — new tests

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-07-16 | Created from exec plan | Morgan (@pm) |
