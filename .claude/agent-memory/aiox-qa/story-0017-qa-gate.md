---
name: story-0017-qa-gate
description: QA Gate CONCERNS for Story 001.7 — Weekly Coverage Report. 2 REQs partially unmet, 3 medium issues.
metadata:
  type: project
---

# QA Gate: Story 001.7 — Weekly Coverage Report

**Verdict:** CONCERNS
**Date:** 2026-07-10
**Gate file:** `docs/qa/gates/001.7-coverage-report.yml`

**Why:** Implementation is functional and robust but 2 ACs not fully met. AC4 (views) is the most significant issue.

## Key Issues

1. **REQ-001 (HIGH):** `coverage_weekly.py` does NOT use `v_coverage_gaps`, `v_coverage_gaps_by_municipio`, or `v_coverage_trend` views defined in Migration 012. Reimplements raw SQL on base tables.
2. **REQ-002 (MEDIUM):** AC2 specifies horizontal bar chart (ASCII + visual) but only a numeric table was implemented.
3. **PERF-001 (MEDIUM):** 7+ separate DB connections per execution (no pooling).
4. **MNT-001 (MEDIUM):** PDF styling code duplicated between `panorama.py` and `coverage_weekly.py`.

**How to apply:** When working on Story 001.7 fixes, prioritize refactoring `fetch_coverage_data()` to use the existing views from Migration 012 before adding features. The `coverage_gaps.py` file already demonstrates correct view usage.
