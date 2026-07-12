---
name: story-COVERAGE-1.4-3.4-created
description: 3 stories COVERAGE-1.4, 3.3, 3.4 criadas no epic-coverage-100pct (2026-07-11)
metadata:
  type: project
---

# COVERAGE-1.4 / 3.3 / 3.4 Stories Created

**Date:** 2026-07-11  
**Agent:** River (SM)  
**Epic:** EPIC-COVERAGE-100PCT  
**Phase:** Master plan execution — 3 missing stories filled

## Stories Created

| Story | File | Priority | Estimate | Executor |
|-------|------|----------|----------|----------|
| COVERAGE-1.4 | `story-COVERAGE-1.4-pncp-v3-coverage-expansion.md` | P1 | 2h | @dev |
| COVERAGE-3.3 | `story-COVERAGE-3.3-multi-source-backfill-pipeline.md` | P1 | 5h | @dev + @data-engineer |
| COVERAGE-3.4 | `story-COVERAGE-3.4-coverage-validation-documentation.md` | P1 | 4h | @analyst |

## Key Design Decisions

- **1.4:** `_ENGINEERING_KEYWORDS` removed completely (not deprecated), rate limit 0.3s, modalidades 1-7, date range 90d. User's ACs supersede previous draft.
- **3.3:** Max 3 iterations (not 5), `_match_entities_cascade()` called after each crawler, SKIP-don't-FAIL on source error. Order: pncp first (highest density), then other sources.
- **3.4:** 5 min/ente investigation protocol, 7 root cause categories, HTML dashboard with gauge, viability assessment of 100% target.

**Why:** User specified exact ACs differing from existing drafts. Files 1.4 and 3.3 were overwritten; 3.4 was created from scratch.

**How to apply:** These stories are now ready for PO validation (Status: Draft -> Ready). Sequence matters: 1.4 -> 3.3 -> 3.4.
