# Story: [12.2 Saídas operacionais] Relatório de source health. · Exportação CSV. · Exportação Excel. (+5 more)

**Story ID:** `ROI-cand-dyn-slice-d58f00f868f0`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T154949Z`)  
**Candidate ID:** `cand-dyn-slice:d58f00f868f0`  
**ROI:** `1.9615`  
**DoD refs:** 12.2 Saídas operacionais, Relatório de source health., Exportação CSV., Exportação Excel., Relatório PDF., Todos os relatórios incluem data de geração.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[12.2 Saídas operacionais] Relatório de source health. · Exportação CSV. · Exportação Excel. (+5 more)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 381f9e1a differs from origin/main fbc58685 (ahead=94, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (233 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.9615 value={'gate_value': 3, 'unlock_power': 3, 'operational_impact': 4, 'risk_reduction': 2, 'evidence_gain': 4} cost={'effort': 3, 'uncertainty': 2, 'external_dependency': 2, 'change_surface': 2}

### Why unlocked

Open local-stage items in section '12.2 Saídas operacionais' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:5c9270b0129a ROI=1.9615 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:6c08d1a1d808 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:d8deaa518e86 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:687b22d210fe ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:59661d935e79 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:d58f00f868f0` only
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

## QA Results

**Reviewer:** Quinn (@qa) — independent  
**Date:** 2026-07-18  
**Verdict:** **PASS**  
**Reviewed revision:** `381f9e1`  
**Evidence:** `docs/ops/session-2026-07-18-operational-export/QA-VERDICT.md`

### DoD item status

| Item | Status |
|------|--------|
| Relatório de source health | DONE |
| Exportação CSV | DONE |
| Exportação Excel | DONE |
| Relatório PDF | DONE |
| data de geração | DONE |
| versão do universo | DONE |
| fonte | DONE |
| status de confiabilidade | DONE |

### Checks

- pytest `tests/test_operational_export_pack.py`: 4 passed
- Live export to `/tmp/ops-export-qa`: exit 0, xlsx=7908B, pdf=2247B
- Metadata fields present on CSV sidecar / Excel / PDF / manifest
- No `LOCAL_READY` positive claim (only forbidden list / “NÃO afirmar”)

### Residual (non-blocking)

- Dead assignment `pdf_text_check` (LOW)
- Unit tests do not cover full `build_pack` DB path (LOW; covered by live CLI)

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | @qa (Quinn) | Independent review → **PASS**; Status InReview→Done; QA-VERDICT.md written |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
