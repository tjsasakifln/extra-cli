# Story: Pacote de evidência: reexecutar testes unitários que provam itens DoD §13/§3 (sem falso verde)

**Story ID:** `ROI-cand-dod-unit-test-evidence-pack`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** InReview  
**Risk level:** **STANDARD**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T233021Z`)  
**Candidate ID:** `cand-dod-unit-test-evidence-pack`  
**ROI:** `4.5172`  
**DoD refs:** §13.1 unit tests, §3 universe baseline 1093

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Pacote de evidência: reexecutar testes unitários que provam itens DoD §13/§3 (sem falso verde)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Cheap high evidence_gain: close many DoD unit-test checkboxes with real pytest of shipped code.

### Evidence of problem

['Current HEAD ef131aa1 differs from origin/main 4da296eb (ahead=13, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Cheap high evidence_gain: close many DoD unit-test checkboxes with real pytest of shipped code.

**Score:** ROI=4.5172 value={'gate_value': 5, 'unlock_power': 4, 'operational_impact': 2, 'risk_reduction': 4, 'evidence_gain': 5} cost={'effort': 2, 'uncertainty': 1, 'external_dependency': 1, 'change_surface': 1}

### Why unlocked

Tests already exist; needs independent re-run + DoD checkbox evidence mapping

### Alternatives discarded

- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dod-unit-test-evidence-pack` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Evidence pack lists each DoD checkbox with pytest nodeid + exit 0
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Only HIGH-confidence mapped items; no mark without re-run
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** DoD.md updated only for proven items after independent QA

---

## Test commands

- `pytest tests/test_universe.py tests/test_common.py tests/test_geocode.py -q`
- `pytest tests/test_coverage_states.py tests/test_freshness_gate.py -q`

---

## Files (planned)

- `docs/ops/session-*/dod-unit-evidence/`
- `DOD.md`
- `docs/stories/*`

---

## Risks

- Over-marking without mapping
- DB-only tests skipped

## Dependencies

- (none)

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

- [ ] @po validated (Ready)
- [ ] @dev implemented on non-main branch
- [ ] Tests/lint per risk level
- [ ] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer)
- [ ] @po closed
- [ ] @devops draft PR / publish path (no auto-merge)
- [ ] DoD.md checkboxes only if evidence authorizes

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
