# Story: [29. Rastreabilidade e auditoria] Cada execução possui erros. · Cada relatório referencia runs de origem. · Mudanças manuais são auditáveis. (+5 more)

**Story ID:** `ROI-cand-dyn-slice-cb906bb58392`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Draft  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-19T135019Z`)  
**Candidate ID:** `cand-dyn-slice:cb906bb58392`  
**ROI:** `2.9241`  
**DoD refs:** 29. Rastreabilidade e auditoria, Cada execução possui erros., Cada relatório referencia runs de origem., Mudanças manuais são auditáveis., Overrides manuais possuem motivo., Overrides manuais possuem data.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[29. Rastreabilidade e auditoria] Cada execução possui erros. · Cada relatório referencia runs de origem. · Mudanças manuais são auditáveis. (+5 more)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 4f2f55aa differs from origin/main dbc5adb2 (ahead=23, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (262 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

**Score:** ROI=2.9241 value={'gate_value': 3, 'unlock_power': 3, 'operational_impact': 3, 'risk_reduction': 4, 'evidence_gain': 5} cost={'effort': 2, 'uncertainty': 2, 'external_dependency': 1, 'change_surface': 2}

### Why unlocked

Open local-stage items in section '29. Rastreabilidade e auditoria' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:b84aad7b10ee ROI=2.9241 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a94b7d79e0a0 ROI=2.7848 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a60989a8e60e ROI=2.5 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:5068b4058697 ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:6a6725b134cb ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:cb906bb58392` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Each of 8 dod_item_ids proven with evidence or left open
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** No NOT_APPLICABLE used to hit campaign meta
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Independent QA PASS before any [x] flip

---

## Test commands

- `python3 -m pytest -q --tb=no -x  # scope to slice tests`

---

## Files (planned)

- `DOD.md`
- `docs/ops/session-*/`
- `tests/*`
- `scripts/*`

---

## Risks

- Over-marking without real evidence
- Partial implementation mistaken for done

## Dependencies

- (none)

## Rollback

Revert last main commit(s) with reverse commit if needed; never force-push; never update DoD on failure.

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
| 2026-07-19 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
