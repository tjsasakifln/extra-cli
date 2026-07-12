---
name: story-COVERAGE-2.4-qa-gate
description: "QA Gate for COVERAGE-2.4 (Entity Coverage Rebuild) — CONCERNS (initial) -> PASS (RE-QA), AC4 resolved, 62+ tests, 0 new ruff errors"
metadata:
  type: project
---

# Story COVERAGE-2.4 QA Gate

**Story:** COVERAGE-2.4 — Entity Coverage Rebuild
**Epic:** EPIC-COVERAGE-100PCT
**Date:** 2026-07-11

## Initial QA: CONCERNS

| Check | Status |
|-------|--------|
| AC1: Rebuild entity_coverage | PASS |
| AC2: Trigger update_entity_coverage() | PASS |
| AC3: Inconsistencias corrigidas | PASS |
| AC4: rebuild-coverage CLI | FAIL — not implemented |
| AC5: Coverage report consistente | PASS |
| AC6: v_unmatched_bids atualizada | PASS |
| AC7: Query verificacao | PASS |
| AC8: pytest + ruff | PASS (48/48 tests) |

**Issue:** REQ-001 (medium) — `cmd_rebuild_coverage()` nao existia na working tree.

## RE-QA: PASS

| Check | Status |
|-------|--------|
| Subcomando no --help | PASS — exibido em positional args |
| cmd_rebuild_coverage() implemented | PASS — 5 steps (reset, init, direct, cnpj_fallback, name_match) |
| Subparser registrado + dispatch | PASS — linhas 819-820 + 845-846 |
| Ruff novos erros | PASS — 0 novos (2 pre-existentes: N806 + F841) |
| pytest | PASS — 62+ tests passando |

**Fix:** `cmd_rebuild_coverage()` implementado em `scripts/local_datalake.py` (linhas 358-515) com 5 passos em cascata, try/except/rollback, e idempotente. Subcomando `python scripts/local_datalake.py rebuild-coverage` funcional.

**Verdict:** PASS — AC4 resolved, REQ-001 closed. DOC-001 and MNT-001 remain as low-severity items.
