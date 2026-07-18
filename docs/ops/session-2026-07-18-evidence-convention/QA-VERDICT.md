# QA Verdict — ROI-cand-dyn-slice-b3ea2a2669e1

**Section:** Convenção de evidência  
**Reviewer:** Quinn (adversarial-qa-auditor, independent)  
**Reviewed commit:** `18f301828d6aceaab41e241e155b2a75e0445e7e`  
**Branch:** `extra-roi/cand-dyn-slice-b3ea2a2669e1`  
**Date:** 2026-07-18  

## Decision: **PASS**

Independent adversarial review. Implementer ≠ reviewer. DoD not flipped by QA.

---

## Scope

| Item | Value |
|------|-------|
| Candidate | `cand-dyn-slice:b3ea2a2669e1` |
| Slice size | 8 of 10 section items (L77–L84) |
| Out of slice | L85 restore, L86 official-source (separate candidate) |
| Implementation | `scripts/ops/evidence_convention.py` |
| Tests | `tests/test_evidence_convention.py` (5 tests) |
| Evidence pack | `docs/ops/session-2026-07-18-evidence-convention/` |

---

## Checks

| Check | Result |
|-------|--------|
| HEAD = `18f3018…` (feat evidence convention) | ✅ |
| 10 catalog kinds match DoD § labels | ✅ |
| DoD L77–L86 still `[ ]` (AC3) | ✅ |
| Empty evidence → completion blocked | ✅ |
| Invalid text `???` → completion blocked | ✅ |
| Catalog JSON (version 1.0.0, 10 kinds) | ✅ |
| Audit advisory + reports 103 without_kind honestly | ✅ |
| No NOT_APPLICABLE abuse | ✅ |
| Live pytest in this subagent | ⚠️ static path (pycache + code map); implementer artifacts present |

---

## Kinds ↔ DoD (10/10)

1. `automated_test` ← teste automatizado reproduzível  
2. `documented_command_exit_0` ← comando documentado com exit code `0`  
3. `system_report` ← relatório JSON/CSV/Excel/PDF/Markdown…  
4. `sql_query` ← consulta SQL com resultado esperado  
5. `run_ledger` ← execução em ledger/manifest/runs  
6. `dated_log` ← log datado e correlacionável  
7. `manual_validation_tiago` ← validação manual por Tiago  
8. `commit_or_pr` ← commit ou PR identificável  
9. `restore_or_recovery_executed` ← teste de restauração/recuperação  
10. `official_source_comparison` ← comparação com fonte oficial (mesma data/período)  

---

## Adversarial falsification

| Attack | Outcome |
|--------|---------|
| `item_may_be_marked_complete([])` | **BLOCKED** |
| `item_may_be_marked_complete(["???"])` | **BLOCKED** |
| Premature DoD `[x]` before QA | **Not present** — all open |
| NA for campaign meta | **Not observed** |
| Weak token date-only / hex-only | **ALLOWED** (residual MEDIUM — heuristic) |

---

## Residual issues (non-blocking)

1. **MEDIUM** — Over-broad regex (date alone, hex alone, bare `json`/`runs`/`log`) can satisfy policy helper without substantive evidence. Tighten if wired as hard gate.  
2. **MEDIUM** — Not wired into campaign/dod_process_integrity flip path (policy library + CLI only).  
3. **LOW** — Story Status still Draft until PO.  
4. **LOW** — Name collision with `reconstruct_evidence.EVIDENCE_KINDS` (different domain).

---

## Claims

**Allowed:** formal 10-kind catalog; empty/invalid blocked; advisory audit honesty; independent QA PASS; AC3 process order.

**Forbidden:** classifier = cryptographic proof; campaign fully gated by this module; LOCAL_READY / VPS / 95% coverage; QA flipped DoD.

---

## Next

1. **@po** close story if accepted.  
2. DoD `[x]` only after PO authorization (QA recommends L77–L84 for this slice; L85–L86 optional if full-section catalog accepted).  
3. Follow-ups: tighten classifier; optional campaign wiring.

**Machine-readable:** `squads/extra-dod-roi/state/qa/ROI-cand-dyn-slice-b3ea2a2669e1.json`
