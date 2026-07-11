---
name: story-td-3.1-qa-gate
description: QA Gate CONCERNS for Story TD-3.1 (Refatorar monitor.py) — 9/10 ACs, 2 issues documented
metadata:
  type: project
---

# Story TD-3.1 QA Gate Result

**Verdict:** CONCERNS
**Date:** 2026-07-11
**Story:** TD-3.1 — Refatorar monitor.py
**Epic:** EPIC-TD-001 (Resolution)

## Summary

- monitor.py de 701 para 186 linhas (-74%) — facade pattern
- 3 modulos extraidos: orchestrator.py (271), entity_matcher.py (277), calculator.py (125)
- 12 unit tests para entity_matcher
- 175/175 testes passando (0 falhas)
- 9/10 ACs met

## Issues

| ID | Severity | Description |
|----|----------|-------------|
| REQ-001 | medium | AC6 parcial — unit tests so para entity_matcher, faltam orchestrator/calculator |
| REL-001 | low | `_coverage_crawl.py:269` importa `_match_entities_cascade` de monitor — funcao movida/renomeada |

## Files Modified

- `docs/qa/gates/td-3.1-refatorar-monitor.yml` (gate decision file)
- `docs/stories/epics/epic-td-001-resolution/story-TD-3.1-refatorar-monitor.md` (status InReview->Done, QA Results, Change Log)

## Decision

**CONCERNS** — non-blocking issues. Proceed to @devops for push after @po review of CONCERNS.
