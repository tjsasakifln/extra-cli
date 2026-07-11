---
name: story-td-5.2-qa-gate
description: QA Gate FAIL for TD-5.2 resume-crawlers — critical runtime import/signature mismatch
metadata:
  type: feedback
---

# Story TD-5.2 QA Gate — FAIL

**Verdict:** FAIL
**Gate file:** `docs/qa/gates/td-5.2-resume-crawlers.yml`

## Critical Findings

### Bug 1: Missing function `is_crawl_completed_today` (HIGH)
`orchestrator.py:28` imports this from `checkpoint.py` — function does not exist anywhere. Would cause `ImportError` at module load time.

### Bug 2: `save_checkpoint` signature mismatch (HIGH)
Orchestrator calls `save_checkpoint(conn, source, ...)` synchronously with psycopg2. `checkpoint.py` defines `async def save_checkpoint(uf, modalidade, ...)` using Supabase async client. Totally incompatible.

### Doc mismatch: docs describe psycopg2 API that doesn't exist in code

## Key Lesson
Previous DoD and self-critique both missed the interface mismatch. The orchestrator was written against an expectation of checkpoint.py that doesn't match the actual implementation. The dev assumed the wrong API existed.

**Why:** The `checkpoint.py` was already committed earlier (initial platform commit) with async Supabase-based design used by `bids_crawler.py`. The new orchestrator was a fresh file that assumed a different API existed.

**How to apply:** When reviewing new code that integrates with existing modules, always verify function signatures exist and match — not just that the import path looks right.
