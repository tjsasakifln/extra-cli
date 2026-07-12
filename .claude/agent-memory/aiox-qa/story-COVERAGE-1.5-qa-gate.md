---
name: story-COVERAGE-1.5-qa-gate
description: FAIL (RE-QA) — 3/9 ACs implemented only in stash, not in working tree (same condition as original FAIL)
metadata:
  type: project
---

# Story COVERAGE-1.5 QA Gate (RE-QA)

**Verdict:** FAIL (RE-QA)
**Date:** 2026-07-11 (second review)

**Key findings:** Same condition as original FAIL. Working tree hash `c4742d7` is IDENTICAL to HEAD. Changes for AC3 (DOM_SC_FULL_DAYS=180), AC4 (endpoint /list), AC8 (_log_municipio_coverage) exist only in stash@{0} (hash `8cbca64`), NOT applied to working tree. Story checkboxes and DoD falsely claim code was "extracted and applied."

**Root cause:** Developer marked ACs as done without applying stash changes to working tree. Stash@{0} has 24 files from multiple stories, cannot `git stash pop` without contamination.

**Issues:** Same 4 high (PROC-001, REQ-003, REQ-004, REQ-008), 1 medium (MNT-001), 1 low (TEST-001)

**Action:** Returned to InProgress. Extract only `scripts/crawl/dom_sc_crawler.py` from stash: `git checkout stash@{0} -- scripts/crawl/dom_sc_crawler.py`
