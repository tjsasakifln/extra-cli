---
name: story-1-1-close
description: Story 1.1 Fix Critical Security closed — 6/6 ACs, CONCERNS, delegacoes @devops
metadata:
  type: project
---

Story 1.1 (Fix Critical Security) closed 2026-07-13.

**ACs:** 6/6 met (SEC-01, SEC-02, SEC-03, TD-001, TD-019, TD-021)
**QA Verdict:** CONCERNS (3 low findings: MNT-001, DOC-001, TST-001)
**Gates:** ruff check PASS, ruff format PASS, bandit PASS, 44/45 tests (1 pre-existing unrelated)
**DoD Report:** 100% (18/18 items)
**Epic status:** InProgress (Sprint 0 complete)

**Pendencias delegadas @devops (nao bloqueiam close):**
- BFG repo-cleaner (remover senha do git history)
- Rotacao de senha do banco
- CodeRabbit review (pre-PR)

**Proxima story:** 1.2 Unify Schema (P0-02)

**Files modified (7):** config/settings.py, .env.example, .env, scripts/crawl/monitor.py, scripts/crawl/bids_crawler.py, scripts/intel_pipeline.py, pyproject.toml
