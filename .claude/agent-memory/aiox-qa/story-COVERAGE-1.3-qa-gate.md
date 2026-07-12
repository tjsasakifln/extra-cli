---
name: story-COVERAGE-1.3-qa-gate
description: FAIR verdict, 2 CRITICAL/HIGH REQs (AC1 not implemented, AC2 stale data), 5 test failures, 1 lint error
metadata:
  type: project
---

## Story COVERAGE-1.3 — Portal Transparencia Batch Detect

**Verdict:** FAIL
**Date:** 2026-07-11

### Key Issues
- **REQ-001 (CRITICAL):** AC1 — 5 platforms (Fiorilli, Iplan, IRI, Prima, Tecnospeed) never added to `_PLATFORM_TEMPLATES` in `transparencia_crawler.py`. Code only has 3 platforms (betha, ipam, egov). Story claims they are "pre-existente" but they do not exist.
- **REQ-002 (HIGH):** AC2 — `data/transparencia_platforms.json` has 2 stub entries instead of documented 295.
- **TST-001/005 (MEDIUM):** 5 tests fail because config expanded from 12 to 79 municipios without updating tests.
- **MNT-001 (LOW):** Unused variable `templates` in `crawl_template()` (ruff F841).

### What Passed
- AC5 (231 residual municipios documented) — PASS
- AC6 (64 detected in config) — PASS
- AC7 (coverage report) — PASS
- AC3/AC4 properly documented as BLOCKED by JS rendering dependency

### Why This Matters
The 5 new platforms are the core deliverable of this story. Without them in `_PLATFORM_TEMPLATES`, the batch detect only tested 3 patterns against 295 municipios, leaving the 5 new platform patterns entirely untested. The story checked AC1 as [x] but the implementation is missing.
