---
name: story-td-8.2-qa-gate
description: QA Gate for story TD-8.2 (Fix Broken Module Imports) — CONCERNS verdict, 15/18 ACs, 3 medium issues (AC6, AC7, AC14)
metadata:
  type: reference
---

# Story TD-8.2 QA Gate

**Verdict:** CONCERNS
**Date:** 2026-07-11

## Results

| Check | Result |
|-------|--------|
| AC Verification | 15/18 PASS, 3 FAIL |
| check_imports.py | 134/134 PASS |
| pytest | 758 passed, 14 failed (all pre-existing) |
| ruff check | 0 new errors in created/modified files |

## Issues

1. **AC6** (medium): `pncp_arp_crawler.py` missing deprecation docstring
2. **AC7** (medium): `pncp_pca_crawler.py` missing deprecation docstring  
3. **AC14** (medium): `rarfile`, `pymupdf4llm`, `pytesseract` not in `requirements.txt`

## Strengths

- 24 stub files created + 9 symlinks enabling 134/134 modules to import cleanly
- Zero regressions in existing tests
- Zero new lint errors
- Lazy imports properly protected (redis_pool, degradation, sentry_sdk)
- Symlinks at `scripts/` level ensure both `scripts.crawl.*` and bare `from clients.*` imports resolve

## Related

- [[story-td-8.1-qa-gate]] — previous cleanup story in same epic
