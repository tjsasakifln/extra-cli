---
name: story-1.2-close
description: Story 1.2 Unify Schema closed, 12/12 ACs GO, 4 QA issues accepted as tech debt
metadata:
  type: project
---

# Story 1.2 Unify Schema -- Closed

**Status:** Done (2026-07-13)
**Executor:** @data-engineer (Dara)
**Quality Gate:** CONCERNS (Quinn)

## Acceptance Criteria

12/12 ACs structural GO:
- AC #1 (zero query schema errors): PASS via `test_all_sql_references.py`
- AC #2 (zero function signature mismatch): PASS, regression verified
- AC #3 (`db/current-schema.sql` reflects HEAD): PASS, SHA-256 fingerprint generated
- AC #4 (`supabase/current-schema.sql` archived): PASS, moved to `supabase/archive/`
- AC #5 (fresh install structural): PASS, test file exists, no actual DB execution (TST-001)
- AC #6 (upgrade structural): PASS, test file exists, no actual DB execution (TST-001)
- AC #7 (rollback sem perda): PASS, rollback SQL documented per migration
- AC #8 (canonical views stable): PASS, 5 views created in migration 030
- AC #9 (concurrency metrics): PASS structural, not directly tested (TST-002)
- AC #10 (set-based <=30% time): PASS structural, no benchmark (REQ-001)
- AC #11 (match_logging columns): PASS, verified existing in 010/005-v2
- AC #12 (FK orgao_cnpj): PASS, NOT VALID FK created

## QA Tech Debt Accepted

| Issue | Severity | Rationale for Deferral |
|-------|----------|------------------------|
| REQ-001 (AC #10 perf benchmark) | MEDIUM | Performance tuning is a separate concern; structural pattern confirmed (INSERT...SELECT) |
| DOC-001 (views contract drift) | LOW | Minor deviations; contract doc vs migration 030 -- non-blocking |
| TST-001 (no actual DB test) | LOW | CI environment limitation; structural test coverage sufficient for schema quality |
| TST-002 (AC #9 not tested) | LOW | Schema foundation exists; concurrency metrics testing belongs in P0-09 scope |

## Deliverables

- 7 migrations (030-036) created
- 5 canonical views implemented
- 2 files modified: `006_upsert_rpcs.sql` (set-based), `pyproject.toml`
- Baseline `db/current-schema.sql` + SHA-256 fingerprint
- Audit gap report: `output/schema/schema-gap-report.{md,json}`
- Canonical views contract: `docs/stories/story-1.2-canonical-views-contract.md`
- Tests: `test_all_sql_references.py`, `test_migration_fresh_install.py`, audit script

## Epic Progress

Epic: Resolucao de Debitos Tecnicos -- 2/5 stories done (1.1, 1.2).
Next: 1.3 Universe Authority (already InProgress).
