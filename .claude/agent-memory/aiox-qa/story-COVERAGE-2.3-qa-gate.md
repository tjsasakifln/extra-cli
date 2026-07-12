---
name: story-COVERAGE-2.3-qa-gate
description: PASS (RE-QA) for COVERAGE-2.3 DOE-SC Crawler Activation — 7/7 issues resolved, 28/28 tests, ruff clean
metadata:
  type: project
---

# Story COVERAGE-2.3 QA Gate

**Gate:** PASS (RE-QA)  
**Date:** 2026-07-11  
**Verdict:** PASS apos FAIL. Todos os 7 issues corrigidos e revalidados no HEAD.

## Original FAIL Issues (all resolved)

- **MNT-001:** `doe_sc` nao registrado em `monitor.py` -> CONFIRMADO: SOURCES line 41, module_map line 564, choices line 598
- **MNT-002:** Login URL `DOE_SC_API_BASE/login` -> CONFIRMADO: `DOE_SC_API_HOST/login` line 142
- **MNT-003:** `diagnostic()` ausente -> CONFIRMADO: `def diagnostic()` line 745
- **MNT-004:** Systemd timer diario/full -> CONFIRMADO: `OnCalendar=Sun` + `--mode incremental`
- **TEST-001:** Sem testes -> 28/28 tests criados e PASS
- **MNT-005:** Ref FEAT-4.1 no service -> CONFIRMADO: "Story COVERAGE-2.3"
- **MNT-006:** Stash nao aplicado -> CONFIRMADO: stash aplicado ao HEAD

## RE-QA Validation

| Check | Result |
|-------|--------|
| `doe_sc` no monitor.py (SOURCES, module_map, choices) | PASS |
| Login URL `DOE_SC_API_HOST/login` | PASS |
| `diagnostic()` presente | PASS |
| pytest 28/28 | PASS |
| ruff clean | PASS |
| Systemd timer Sun + service --mode incremental | PASS |

## ACs

AC1-AC3, AC7-AC8 = GO. AC4-AC6 = BLOCKED (credentiais externas).

See [[story-COVERAGE-1.2-qa-gate]] for related CIGA CKAN story.
