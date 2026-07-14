---
name: story-1.1-fix-critical-security
description: CONCERNS verdict for Story 1.1 (Fix Critical Security). 6/6 ACs met, 44/45 tests (1 pre-existing), 3 low issues (MNT-001, DOC-001, TST-001).
metadata:
  type: project
---

# Story 1.1 QA Gate

**Verdict:** CONCERNS
**Gate file:** `docs/qa/gates/1.1-fix-critical-security.yml`
**Date:** 2026-07-13

## Summary

| Dimension | Result |
|-----------|--------|
| Acceptance Criteria | 6/6 PASS |
| Tests | 44/45 PASS (1 pre-existing: `test_smoke_sql_views_syntax` -- `QUERY_ATIVOS_90_180` import, not related) |
| Regressions | 0 (confirmed via `git stash`) |
| ruff check | 0 errors |
| ruff format | 0 errors |
| bandit (S rules) | 0 errors |
| Hardcoded credentials in modified files | 0 |
| SQL f-strings (AST scan) | 0 |

## Issues

- MNT-001 (low): bids_crawler.py deprecated but fix applied correctly
- DOC-001 (low): DoD 14-15 pending (BFG, manifest) -- delegated to @devops
- TST-001 (low): No dedicated tests for config/import changes

## Files Modified (6)

- `config/settings.py` -- SEC-03: DATABASE_URL env var, no hardcoded password
- `.env.example` -- SEC-02/TD-021: GOOGLE_APPLICATION_CREDENTIALS, DATABASE_URL, PNCP_BASE v3
- `.env` -- TD-021: PNCP_BASE v3
- `scripts/crawl/monitor.py` -- SEC-01: psycopg2.sql.Identifier replaces f-string SQL
- `scripts/crawl/bids_crawler.py` -- TD-001: sys.path.insert for ingestion.* imports
- `scripts/intel_pipeline.py` -- TD-019: sys.path.insert for lib.cli_validation imports
- `pyproject.toml` -- SEC-01: bandit S rules in lint.select

## Pending (delegated to @devops)

- BFG repo-cleaner (remove password from git history)
- Database password rotation
- CodeRabbit review (timeout on free plan)
- Pre-PR: coderabbit --base main review
- Pre-Deployment: security scan
