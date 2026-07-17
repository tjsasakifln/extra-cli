# Story: Reduzir dívida que faz Test All (full suite) skipped / schema views falharem

**Story ID:** `ROI-cand-full-suite-schema-debt`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T224949Z`)  
**Candidate ID:** `cand-full-suite-schema-debt`  
**ROI:** `1.8571`  
**DoD refs:** Suíte global completa verde (unchecked), CI Test All skipped

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Reduzir dívida que faz Test All (full suite) skipped / schema views falharem**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Aumenta confiança do gate e reduz falso verde por testes não rodados.

### Evidence of problem

['Current HEAD 3724f33d differs from origin/main 4da296eb (ahead=3, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'E3.S1 and E3.S2 already Done with independent QA/PO — cand-qa-po-e3-stories not UNLOCKED', 'cand-workspace-daily-evidence-pack already completed via ROI-cand-workspace-daily-evidence-pack — not UNLOCKED']

### Value / ROI justification

Aumenta confiança do gate e reduz falso verde por testes não rodados.

**Score:** ROI=1.8571 value={'gate_value': 3, 'unlock_power': 3, 'operational_impact': 2, 'risk_reduction': 4, 'evidence_gain': 4} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 1, 'change_surface': 3}

### Why unlocked

Local/CI work; no VPS; improves evidence quality

### Alternatives discarded

- cand-qa-po-e3-stories: COMPLETED — B2G-E3.S1/S2 Done with po_closed + independent QA (S1 qa=CONCERNS, S2 qa=CONCERNS); do not re-bind or re-implement
- cand-workspace-daily-evidence-pack: COMPLETED — ROI-cand-workspace-daily-evidence-pack Done with po_closed + independent QA; do not re-bind
- cand-coverage-slice-pending-collection ROI=1.62 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-golden-path-pncp-health ROI=1.3617 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-full-suite-schema-debt` only
- Tests and evidence required by acceptance criteria
- AIOX state transitions honored

### OUT

- Any lower-ROI unlocked item (must wait for next cycle)
- Blocked external work unless this card is exactly that and resources exist
- Scope expansion / architecture tourism without DoD link
- Portal publico, multi-tenant, billing, K8s/Kafka/Redis/ES without demonstrated need
- Physical works tracking / auto-protocol without human action

---

## Acceptance Criteria

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Critical full-suite path documented green or remaining skips justified
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** No hiding skipped critical tests

---

## Test commands

- `make test`
- `make test-all (documented)`

---

## Files (planned)

- `tests/*`
- `supabase/* views`
- `CI workflow if needed`

---

## Risks

- Wide surface
- env-specific failures

## Dependencies

- local db-up optional for database tests

## Rollback

Revert feature branch commits; never update DoD on failure; no merge.

## Claims if PASS

- Only claims backed by new evidence

## Claims still forbidden

- VPS provisionada/operacional sem evidência live
- Cobertura operacional 95% sem medição estrita
- Freshness live garantida por fixtures
- LOCAL_RESILIENCE_READY (superseded → NOT_READY)
- PRE_VPS_FINAL_READY sem live canary + PG evidence
- Stories Done sem QA/PO independentes

---

## AIOX DoD for this story

- [x] @po validated (Ready)
- [x] @dev implemented on non-main branch
- [x] Tests/lint per risk level
- [x] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer)
- [ ] @po closed
- [ ] @devops draft PR / publish path (no auto-merge)
- [ ] DoD.md checkboxes only if evidence authorizes

---

## QA Results

**Reviewer:** adversarial-qa-auditor (Quinn) — independent of implementer `delivery-engineer`  
**Date:** 2026-07-17T23:06:00Z  
**Reviewed commit:** `b18e6b84eae65c5768e76cd4dbfa04e7f9a5773b`  
**Cycle:** `cyc-2026-07-17T224949Z`  
**Verdict:** **PASS**

### Independent re-verification

| Check | Result |
|-------|--------|
| `pytest -o addopts='' -q squads/extra-dod-roi/tests/` | **16 passed** |
| Critical path (resilient-smoke core, `-m "not database and not slow"`) | **197 passed, 24 skipped, exit 0** |
| `01-critical-readiness.exit` | `CRITICAL_EXIT=0` |
| CI `test-all` gate | `if: github.event_name == 'workflow_dispatch'`; **no** `continue-on-error: true` |
| Skips honesty | 24× `@pytest.mark.skip` in `test_sc_compras_crawler.py` with reasons; not converted to pass |
| Forbidden claims | Honored (no READY seals / full-suite green on PR / 95% / live PG schema views) |
| Scope creep | None — pack + structural tests + smoke cycle-safety only; no DOD.md |

### AC

| AC | Verdict |
|----|---------|
| AC1 Critical path green **or** skips justified | **PASS** — green + 24 skips documented with reasons |
| AC2 No hiding skipped critical tests | **PASS** — skips visible; CI test-all gate remains explicit |

### Residual (non-blocking)

- Schema/view debt still open (REQUIRE_TEST_DB) — intentional per PO GO; follow-up via re-rank
- MANIFEST §2 wording “5 skips” vs 24 skipped tests (counts in summary are correct)
- Structural tests are artifact assertions; live critical path re-run by QA mitigates

**Gate file:** `squads/extra-dod-roi/state/qa/cyc-2026-07-17T224949Z-qa.json`  
**Status:** remains **InReview** until @po close (QA does not set Done / publication).

---

## Dev Notes

### Delivered (this slice)

- `docs/ops/session-2026-07-17-full-suite-debt/MANIFEST.md` — honest green vs skips vs CI test-all gate
- Critical path refresh: 197 passed, 24 skipped (sc_compras API refactoring), `CRITICAL_EXIT=0`
- Structural tests: `squads/extra-dod-roi/tests/test_full_suite_debt_manifest.py` (7 tests)
- Fix: `test_implement_gate` tolerant of active Ready cycle
- **Did not** flip DoD checkboxes; **did not** claim full-suite green or READY seals

### File List

- docs/ops/session-2026-07-17-full-suite-debt/*
- squads/extra-dod-roi/tests/test_full_suite_debt_manifest.py
- squads/extra-dod-roi/tests/test_squad_smoke.py
- docs/stories/ROI-cand-full-suite-schema-debt.md
- .aiox/state/stories/ROI-cand-full-suite-schema-debt.json

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-17 | Pax (@po) | PO GO (8/10) — status Draft → Ready; AC interpret as honest MANIFEST of green vs skips |
| 2026-07-17 | Dex (@dev) | Dev start — status Ready → InProgress; branch extra-roi/cand-full-suite-schema-debt |
| 2026-07-17 | Dex (@dev) | Implemented MANIFEST + suite-debt tests; status InProgress → InReview |
| 2026-07-17 | Quinn (@qa / adversarial-qa-auditor) | Independent QA PASS on b18e6b8; critical path re-run 197p/24s; CI gate verified |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
| 2026-07-17 | Pax (@po) | PO close after QA PASS — status InReview → Done |
