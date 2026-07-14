---
name: story-1.3-close
description: Story 1.3 Universe Authority closed, 6/11 ACs structural GO, 5 QA issues accepted as tech debt
metadata:
  type: project
---

# Story 1.3 Universe Authority -- Closed

**Status:** Done (2026-07-13)
**Executor:** @dev (Dex)
**Quality Gate:** CONCERNS (Quinn)

## Acceptance Criteria Assessment

6/11 ACs fully met (structural GO):

| AC | Description | Status | Notes |
|----|-------------|--------|-------|
| #1 | Todas metricas retornam mesmo denominador 1.093 | PARTIAL | DB-dependent; core infra ready |
| #2 | Zero WHERE raio_200km IS TRUE em queries analiticas | NOT MET | ~50 files pending -- tracked as REQ-001 |
| #3 | Mudanca de seed produz novo snapshot sem alterar artefatos | MET | Implemented in universe_tools.py |
| #4 | 1.093 entes incluidos e 992 excluidos | DB-DEP | Code ready, requires migration 037 applied |
| #5 | 0 unresolved | DB-DEP | Ledger code ready |
| #6 | universe_run_id em todas queries analiticas | PARTIAL | contract_intel/cli.py and local_datalake.py pending -- REQ-002 |
| #7 | Bloqueio execucao exit code 42 | MET | check_seed() implemented |
| #8 | Ledger de divergencia funcional | MET | divergence command implemented |
| #9 | Raiz 00394494 resolvida manualmente | MET | Decision record: docs/decisions/universe-00394494-duplicate-root-resolution.md |
| #10 | Configuracoes de ambiente separadas (TD-034) | MET | .env.dev, .env.staging, .env.production |
| #11 | Subprocess JSON estruturado com run_id (TD-005) | MET | --pipeline-json flag in intel_pipeline.py |

## QA Tech Debt Accepted

| Issue | Severity | Category | Rationale for Deferral |
|-------|----------|----------|------------------------|
| REQ-001 (AC2 ~50 raio_200km) | MEDIUM | Requirements | Mechanical migration of table references; core infra ready. Tracked as follow-up epic backlog item. |
| REQ-002 (AC6 contract_intel pending) | MEDIUM | Requirements | Two files pendentes (contract_intel/cli.py, local_datalake.py). Non-architectural changes. |
| TST-001 (0% coverage universe_tools/universe_query) | MEDIUM | Tests | 180+18 lines uncovered. Well-structured for testing. DoD coverage target deferred. |
| MNT-001 (ruff format pending) | LOW | Maintenance | Formatting only, no logic impact. |
| MNT-002 (E501 line too long) | LOW | Maintenance | Line 473 in universe_tools.py, cosmetic. |

## Deliverables

- 2 migrations: 037_target_universe_snapshot.sql, 038_target_universe_active_view.sql
- 2 scripts: universe_tools.py (CLI), universe_query.py (SQL helpers)
- 3 .env files: .env.dev, .env.staging, .env.production
- 1 decision record: universe-00394494-duplicate-root-resolution.md
- 1 runbook: universe-snapshot-runbook.md
- 5 files modified: consulting_readiness.py, intel_pipeline.py, manifest.py, backfill.py, panorama.py

## Decision: Partial ACs Accepted as Follow-up

AC2 (~50 files raio_200km migration) and AC6 (contract_intel, local_datalake universe_run_id) are accepted as follow-up. Rationale:
- Core infrastructure (snapshot tables, ledger, blocking, env separation, JSON output) is complete and high quality
- Remaining work is mechanical query migration, not architectural
- Each pending file is a predictable, scoped change (replace table reference + add JOIN)
- Documented in epic backlog as follow-up tasks

## Epic Progress

Epic: Resolucao de Debitos Tecnicos -- 3/5 stories done (1.1, 1.2, 1.3).
Next: 1.4 Reconcile Open Tenders (Ready, pending dev start).
