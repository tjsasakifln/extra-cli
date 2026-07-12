---
name: story-COVERAGE-1.4-qa-gate
description: QA Gate CONCERNS verdict for COVERAGE-1.4 — PNCP v3 Coverage Expansion
metadata:
  type: reference
---

# Story COVERAGE-1.4 QA Gate

**Verdict:** CONCERNS
**Date:** 2026-07-11
**Story:** COVERAGE-1.4 — PNCP v3 Coverage Expansion (EPIC-COVERAGE-100PCT)

## AC Status

| AC | Status | Detail |
|----|--------|--------|
| AC1 | PASS | `_ENGINEERING_KEYWORDS` completamente removido |
| AC2 | PASS | `INGESTION_MODALIDADES` default = "1,2,3,4,5,6,7" |
| AC3 | PASS | `INGESTION_DATE_RANGE_DAYS` default = 90 |
| AC4 | PASS | `PNCP_REQUEST_DELAY` default = 0.3 |
| AC5 | PENDING | Crawl full bloqueado por execucao em producao |
| AC6 | PENDING | Dependente de AC5 |
| AC7 | PENDING | Dependente de AC5/AC6 |
| AC8 | PASS | 24/24 PNCP tests pass, ruff 0 erros |

## Issues

- **REQ-001** (medium): AC5 pendente — crawl full nao executado
- **REQ-002** (medium): AC6 pendente — medicao de ganho nao realizada
- **REQ-003** (medium): AC7 pendente — relatorio de expansao pre-existente com delta -3 (dado pre-expansao)
- **MNT-001** (low): Report de expansao existente pode causar confusao se interpretado como resultado da expansao

## Key Observations

- All code-level ACs (AC1-AC4, AC8) properly implemented and verified
- 3 pending ACs (AC5-AC7) are operationally blocked by production execution, clearly documented in the story
- `docs/epic-coverage/pncp-expansion-report.md` exists with baseline 774 entities but delta -3 — this is pre-expansion data
- Test `test_transform_filters_by_keyword` replaced with `test_transform_no_keyword_filtering`

## Files Modified

- `scripts/crawl/pncp_crawler_adapter.py`
- `tests/test_crawler_pncp.py`
