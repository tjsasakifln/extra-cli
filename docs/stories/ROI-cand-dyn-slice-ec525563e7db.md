# Story: [Pacote final da consultoria] O sistema gera PDF executivo e planilhas Excel a partir do m · PDF e Excel usam a mesma data de corte, universo, filtros e  · Divergências entre PDF e Excel são detectada

**Story ID:** `ROI-cand-dyn-slice-ec525563e7db`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Draft  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T184610Z`)  
**Candidate ID:** `cand-dyn-slice:ec525563e7db`  
**ROI:** `1.2261`  
**DoD refs:** Pacote final da consultoria, O sistema gera PDF executivo e planilhas Excel a partir do mesmo conjunto de run, PDF e Excel usam a mesma data de corte, universo, filtros e versão do perfil., Divergências entre PDF e Excel são detectadas automaticamente., O PDF possui estrutura suficiente para uma entrega executiva de aproximadamente , O Excel contém dados rastreáveis, filtros e abas necessárias à revisão.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[Pacote final da consultoria] O sistema gera PDF executivo e planilhas Excel a partir do m · PDF e Excel usam a mesma data de corte, universo, filtros e  · Divergências entre PDF e Excel são detectada**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 74667830 differs from origin/main fbc58685 (ahead=161, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (251 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close', 'Candidate cand-dyn-slice:5e47929809f6 marked COMPLETED: ROI-cand-dyn-slice-5e47929809f6 Done with independent QA/PO (leave-open or partial DoD does not re-bind same dyn slice)']

### Value / ROI justification

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.2261 value={'gate_value': 2, 'unlock_power': 2, 'operational_impact': 2, 'risk_reduction': 2, 'evidence_gain': 3} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 2, 'change_surface': 2}

### Why unlocked

Open local-stage items in section 'Pacote final da consultoria' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:6b161046b92a ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:79cd98a48651 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:cc064fecd554 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a23a60867cfd ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:87b662ba0e0b ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:ec525563e7db` only
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
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
