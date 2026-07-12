---
name: story-COVERAGE-1.7-qa-gate
description: 'QA Gate for COVERAGE-1.7 — Gap Analysis Report. Verdict: CONCERNS, 8/8 ACs, 32/32 tests, 1 medium issue (MNT-001)'
metadata:
  type: project
---

# Story COVERAGE-1.7 QA Gate

**Verdict:** CONCERNS (InReview -> Done)
**Date:** 2026-07-11
**Reviewer:** Quinn (Guardian)

## Summary

- **ACs:** 8/8 met — scripts executados (coverage_gaps.py, coverage_weekly.py), relatorio consolidado gerado
- **Tests:** 32/32 pass (test_coverage_calculator + test_report_dedup)
- **Ruff:** 0 errors (19 N806 naming convention warnings — cosmetic only)
- **Artifacts:** Markdown report (252 linhas, 10 secoes), XLSX gaps (128KB), PDF (6.8KB), XLSX detalhado (65KB)

## Issues

| ID | Severity | Description |
|----|----------|-------------|
| MNT-001 | medium | Bugfix `e.uf` -> `NULL AS uf` na File List nao confere com codigo (linha 128 ainda usa `e.uf`). Codigo sem diff no git. |

## Key Details

- Report covers 2.085 entes SC, 39.4% coverage, 1.264 gaps
- Top-50 entidades prioritarias listadas com fonte recomendada
- Recomendacoes P0-P2 para Fase 2 (DOM-SC, CIGA CKAN, PCP, TCE-SC, PNCP, BigQuery)
- Trend analysis: 5 snapshots (S24-S28), ~+15 entes/semana, +0.7pp/semana

**Why:** This is an analysis/report story with no application code changes. The single concern is a documentation-code mismatch around the `e.uf` fix claim, which does not block the story as the reports were successfully generated.

## References
- Gate file: `docs/qa/gates/COVERAGE-1.7-qa-gate.yaml`
- Story: `docs/stories/epics/epic-coverage-100pct/story-COVERAGE-1.7-gap-analysis-report.md`
