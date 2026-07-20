# QA Verdict — ROI-cand-dyn-slice-cb906bb58392

**Section:** 29. Rastreabilidade e auditoria (slice 8 items)  
**Reviewer:** Quinn (@qa) — independent adversarial auditor  
**Implementer:** @dev (Dex) — ≠ reviewer  
**Reviewed commit:** `880bc00fe95eb52ae8bfa76c2dbbe6a65f4f6da7`  
**Branch:** `goal/roi-rastreabilidade-cb906bb58392`  
**Date:** 2026-07-20  

## Decision: **CONCERNS** (acceptable — DoD flips 1–6 authorized)

Independent adversarial review. Primary ACs met. Residual soft-fail audit-loss risk documented (non-blocking).

---

## Scope

| Item | Value |
|------|-------|
| Candidate | `cand-dyn-slice:cb906bb58392` |
| Slice | 8 open DoD items in §29 |
| Primary proven | items 1–6 |
| Left OPEN | items 7–8 (coverage/freshness reconstruct) |
| Implementation | `scripts/ops/run_execution_ledger.py` (+ CLI, override bridge) |
| Library | `scripts/lib/manual_override_ledger.py` (REUSE) |
| Tests | 19 passed (QA re-run) |
| Evidence pack | this directory |

---

## Checks (QA re-executed)

| Check | Result |
|-------|--------|
| HEAD = `880bc00…` | ✅ |
| `pytest` ledger suite 19 passed | ✅ (QA re-run exit 0) |
| `ruff check` touched files | ✅ All checks passed |
| CLI `--help` record/verify/override/mutation | ✅ |
| Demo `verify` ok=true, n_runs=2, unlinked=[] | ✅ (checksum match stored) |
| Fail-closed blank autor | ✅ rc=2 |
| Fail-closed blank motivo | ✅ rc=2 |
| Fail-closed blank data | ✅ ValueError |
| Fail-closed blank mutation actor | ✅ rc=2 |
| `errors[]` always present | ✅ |
| `report_run_links` always link run_id | ✅ |
| Items 7–8 remain OPEN | ✅ |
| No LOCAL_READY / 95% / PRE_VPS / full §29 | ✅ |
| No NOT_APPLICABLE abuse | ✅ |
| DoD [x] only after independent QA | ✅ (flips applied by @qa) |
| Soft-fail callers ignore return value | ⚠️ CONCERNS |

---

## AC traceability

| AC | Verdict | Evidence |
|----|---------|----------|
| 1. Each of 8 dod_item_ids proven or left open | ✅ | dod-map.md: 1–6 PROPOSED→DONE; 7–8 OPEN |
| 2. No NOT_APPLICABLE for campaign meta | ✅ | OPEN items stay `[ ]` |
| 3. Independent QA before any [x] flip | ✅ | flips applied only after this verdict |

---

## Adversarial falsification

| Attack | Outcome |
|--------|---------|
| Empty autor on override CLI | **BLOCKED** (rc=2, ok=false) |
| Empty motivo on override CLI | **BLOCKED** (rc=2) |
| Blank data via lib | **BLOCKED** (ValueError) |
| Blank mutation actor | **BLOCKED** (rc=2) |
| Omitting errors= on record_execution | **SAFE** — writes `errors: []` |
| Report without run link | **BLOCKED** by invariant when recorded via API |
| Claim full §29 / LOCAL_READY / 95% | **NOT present** in implementer artifacts |
| Flip 7–8 without evidence | **NOT proposed** — correctly OPEN |
| Soft-fail I/O on decision_pack path | **RESIDUAL** — return value not checked (CONCERNS) |

---

## Residual issues (non-blocking)

1. **MEDIUM — soft-fail audit loss:** `record_execution_safe` returns `{"ok": False, ...}` on I/O failure. Callers `decision_pack` / `weekly_cycle` ignore the return value; outer `try/except` never fires because safe does not raise. Operator can complete a pack with exit 0 while losing the audit row.  
   **Recommendation (follow-up story):** log to stderr + append to report warnings when `result.get("ok") is False`. Do not make ledger I/O hard-fail packs without product decision.

2. **LOW — partial wiring:** “Cada relatório referencia runs de origem” is proven for ledger-recorded runs (CLI + decision_pack + weekly_cycle), not every report generator in the monorepo. Honest PARTIAL §29 advance — acceptable for slice.

3. **LOW — process:** story header still said Draft at review start; state `po_validated` was false despite Ready→InProgress transitions in Dev Agent Record. PO close should reconcile.

---

## DoD flips applied by @qa

| # | Item | Action |
|---|------|--------|
| 1 | Cada execução possui erros. | **[x]** |
| 2 | Cada relatório referencia runs de origem. | **[x]** |
| 3 | Mudanças manuais são auditáveis. | **[x]** |
| 4 | Overrides manuais possuem motivo. | **[x]** |
| 5 | Overrides manuais possuem data. | **[x]** |
| 6 | Overrides manuais possuem autor. | **[x]** |
| 7 | A evidência de coverage pode ser reconstruída. | **OPEN** (no flip) |
| 8 | A evidência de freshness pode ser reconstruída. | **OPEN** (no flip) |

---

## Claims

**Allowed after this verdict:** PARTIAL §29 advance on the six flipped items with automated tests + session evidence + QA CONCERNS.

**Still forbidden:** full §29 complete · LOCAL_READY · operational 95% · PRE_VPS_FINAL_READY · VPS operational · LOCAL_RESILIENCE_READY.

---

## Gate file

`docs/qa/gates/ROI-cand-dyn-slice-cb906bb58392.yml`

## Next

@po close story → @devops publish path (no auto-merge). Follow-up optional: soft-fail operator notice.
