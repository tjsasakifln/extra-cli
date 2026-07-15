---
name: cm-07-validation
description: CM-07 Bootstrap PCP expand validated GO 8.0/10, Draft->Ready, epic alignment condition
metadata:
  type: reference
---

# CM-07 Validation Result

**Story:** CM-07 Bootstrap Local DB e Expansao de Cobertura PCP
**File:** `docs/stories/CM-07-bootstrap-pcp-expand.md`
**Validation Date:** 2026-07-15
**Score:** 8.0/10
**Verdict:** GO (conditional)

## Scoring

| Dimension | Score |
|-----------|-------|
| Clareza | 9/10 |
| ACs Given/When/Then | 10/10 |
| Escopo IN/OUT | 10/10 |
| Dependencias/riscos | 6/10 |
| Baseline/alvo | 8/10 |
| Arquivos afetados | 9/10 |
| DoD | 8/10 |
| NFR/divida | 6/10 |
| Alinhamento epic | 5/10 |
| Clareza tecnica | 9/10 |

## Critical Issue: Epic Alignment

Epic `EPIC-COVERAGE-MAX-200KM` defines CM-07 as "DOM-SC coverage validation", but the story is about "PCP expansion + DB bootstrap" (which matches epic's CM-08). The epic must be reconciled before implementation.

## Condition

Must resolve CM-07/CM-08 epic identity conflict before @dev implementation starts.

## Verified Technical Claims

- `SOURCE_BLOCKERS` line 48: `"pcp": "Portal requer Selenium + CAPTCHA"` -- CONFIRMED
- `bootstrap_local.sh` uses `python` not `python3`, path `scripts/db/` wrong -- CONFIRMED
- Seed exists at `db/seed/seed_sc_entities.py` -- CONFIRMED
- PCP crawler defaults to 30 days full mode -- CONFIRMED
- 7 migration files in `supabase/migrations/` -- CONFIRMED
- `tests/test_pcp_crawler.py` exists -- CONFIRMED
