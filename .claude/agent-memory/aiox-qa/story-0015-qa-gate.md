---
name: story-0015-qa-gate
description: Story 001.5 QA Gate — CONCERNS verdict, 3 issues documented
metadata:
  type: project
---

**Story:** 001.5 - Coverage Baseline + Monitoring Dashboard
**Verdict:** CONCERNS
**Date:** 2026-07-10
**Gate file:** `docs/qa/gates/story-001.5-coverage-monitoring-gate.yaml`

**Issues found:**
1. **MEDIUM** (code): Trend query hardcodes `source = 'total'` but `generate_coverage_snapshot()` never inserts a 'total' row. Trend section in the CLI dashboard is always empty even after snapshots are generated.
2. **LOW** (code): `ON CONFLICT DO NOTHING` in `generate_coverage_snapshot()` has no UNIQUE constraint to conflict against — duplicate rows possible if called multiple times same day.
3. **LOW** (docs): Snapshot table retention >365 days (flagged as risk in story) not implemented in `pncp-purge.service`.

**Why:** Story implements coverage baseline, gap analysis views, CLI dashboard, and Excel export -- 9/10 ACs fully met. The trend bug (issue #1) is real but non-blocking since the dashboard renders all other sections correctly.

**How to apply:** When reviewing coverage-related stories in EPIC-001, verify that the trend aggregation fix is included, or flag it as a follow-up. The `coverage_snapshots` table schema may need a UNIQUE constraint added for correctness.
