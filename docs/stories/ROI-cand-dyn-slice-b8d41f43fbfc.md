# Story: [Estados, aplicabilidade e bloqueio] Um item desmarcado permanece não aceito, mesmo que esteja pa · Um requisito somente pode ser tratado como `NOT_APPLICABLE`  · `NOT_APPLICABLE` possui justificativa

**Story ID:** `ROI-cand-dyn-slice-b8d41f43fbfc`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T172517Z`)  
**Candidate ID:** `cand-dyn-slice:b8d41f43fbfc`  
**ROI:** `1.2261`  
**DoD refs:** Estados, aplicabilidade e bloqueio, Um item desmarcado permanece não aceito, mesmo que esteja parcialmente implement, Um requisito somente pode ser tratado como `NOT_APPLICABLE` quando a própria red, `NOT_APPLICABLE` possui justificativa, data e evidência; não é usado para contor, Campo indisponível na fonte é registrado como `SOURCE_UNAVAILABLE` ou `NOT_READY, Um blocker externo não desaparece do gate; ele permanece visível até resolução o

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[Estados, aplicabilidade e bloqueio] Um item desmarcado permanece não aceito, mesmo que esteja pa · Um requisito somente pode ser tratado como `NOT_APPLICABLE`  · `NOT_APPLICABLE` possui justificativa**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 7 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 67a87b1d differs from origin/main fbc58685 (ahead=119, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (234 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close', 'Candidate cand-dyn-slice:5e47929809f6 marked COMPLETED: ROI-cand-dyn-slice-5e47929809f6 Done with independent QA/PO (leave-open or partial DoD does not re-bind same dyn slice)']

### Value / ROI justification

Dynamic slice of 7 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.2261 value={'gate_value': 2, 'unlock_power': 2, 'operational_impact': 2, 'risk_reduction': 2, 'evidence_gain': 3} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 2, 'change_surface': 2}

### Why unlocked

Open local-stage items in section 'Estados, aplicabilidade e bloqueio' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:b3ea2a2669e1 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:2b83aa82a369 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:dd7b4910d7f9 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a6cf12911b22 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:8d8c11884fa6 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:b8d41f43fbfc` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Each of 7 dod_item_ids proven with evidence or left open
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
- [x] @qa independent verdict PASS (re-review @ 58d9a83)
- [x] @po closed
- [x] @devops merge into epic branch path
- [x] DoD.md checkboxes only if evidence authorizes (after QA PASS)

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | @po | STORY_READY (validate GO) |
| 2026-07-18 | @dev | implement requirement_states; first QA FAIL; remediate |
| 2026-07-18 | @qa independent | re-review PASS @ 58d9a83 |
| 2026-07-18 | @po | close after PASS; authorize DoD flips with evidence |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
