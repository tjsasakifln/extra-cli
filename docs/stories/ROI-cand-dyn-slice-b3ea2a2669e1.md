# Story: [Convenção de evidência] teste automatizado reproduzível; · comando documentado com exit code `0`; · relatório JSON, CSV, Excel, PDF ou Markdown gerado pelo sist (+5 more)

**Story ID:** `ROI-cand-dyn-slice-b3ea2a2669e1`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T175632Z`)  
**Candidate ID:** `cand-dyn-slice:b3ea2a2669e1`  
**ROI:** `1.2261`  
**DoD refs:** Convenção de evidência, teste automatizado reproduzível;, comando documentado com exit code `0`;, relatório JSON, CSV, Excel, PDF ou Markdown gerado pelo sistema;, consulta SQL com resultado esperado;, execução registrada em ledger, manifest ou tabela de runs;

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[Convenção de evidência] teste automatizado reproduzível; · comando documentado com exit code `0`; · relatório JSON, CSV, Excel, PDF ou Markdown gerado pelo sist (+5 more)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD de89e89b differs from origin/main fbc58685 (ahead=124, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (235 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close', 'Candidate cand-dyn-slice:5e47929809f6 marked COMPLETED: ROI-cand-dyn-slice-5e47929809f6 Done with independent QA/PO (leave-open or partial DoD does not re-bind same dyn slice)']

### Value / ROI justification

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.2261 value={'gate_value': 2, 'unlock_power': 2, 'operational_impact': 2, 'risk_reduction': 2, 'evidence_gain': 3} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 2, 'change_surface': 2}

### Why unlocked

Open local-stage items in section 'Convenção de evidência' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:2b83aa82a369 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:dd7b4910d7f9 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a6cf12911b22 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:8d8c11884fa6 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:4e59455a8fc4 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:b3ea2a2669e1` only
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
- [x] @qa independent verdict PASS @ 18f3018
- [x] @po closed
- [x] @devops merge into epic
- [x] DoD.md checkboxes only if evidence authorizes (after QA PASS)

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
