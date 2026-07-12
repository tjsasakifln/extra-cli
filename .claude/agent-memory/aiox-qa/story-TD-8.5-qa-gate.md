---
name: story-TD-8.5-qa-gate
description: QA Gate verdict for Story TD-8.5 — Multi-Source Backfill — FAIL verdict with 5 HIGH issues
metadata:
  type: reference
---

# Story TD-8.5 QA Gate

**Verdict:** FAIL
**Date:** 2026-07-11

## Summary

Multi-source backfill story with 11 ACs. Only AC6 (PCP Scale) fully met. 7/11 ACs not met. Story returned to @dev.

## Key Issues

### HIGH (5)
- **H-001**: Task 7.2 misrepresentation — DOE-SC not added to monitor.py (ciga_ckan was added instead)
- **H-002**: Task 5.1 fix not applied — compras_gov_crawler.py still uses old API params (dataInicial, resultado)
- **H-003**: AC4 target not met — 75/295 municipios detected vs >= 200 required
- **H-004**: AC10 coverage far below target — 39.4% vs 85%+
- **H-005**: Test regressions — 15+ failures including transparencia config mismatch

### MEDIUM (3)
- M-001: PCP_MAX_PAGES_V2 constant doesn't exist (should be PCP_MAX_PAGES)
- M-002: Duplicate Task 2.4 (one checked, one unchecked)
- M-003: AC3/Task 6.2 inconsistency — AC marked done but full crawl not complete

### LOW (3)
- L-001: 348 ruff errors (baseline comparison needed)
- L-002: SyntaxError in test_transparencia_crawler.py (pre-existing)
- L-003: AC1/AC2 blockers documented correctly

## Story File
`docs/stories/epics/epic-td-003-reversa-remediation/story-TD-8.5-multi-source-backfill.md`

## Test Results
779 passed, 26 failed (no-cov run), 2 warnings
