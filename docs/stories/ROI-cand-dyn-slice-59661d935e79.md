# Story: [7.2 Matriz ente × fonte × capability] Cada ente possui decisão de aplicabilidade para editais. · Cada ente possui decisão de aplicabilidade para contratos. · A aplicabilidade pode variar por capabili

**Story ID:** `ROI-cand-dyn-slice-59661d935e79`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T160508Z`)  
**Candidate ID:** `cand-dyn-slice:59661d935e79`  
**ROI:** `1.8067`  
**DoD refs:** 7.2 Matriz ente × fonte × capability, Cada ente possui decisão de aplicabilidade para editais., Cada ente possui decisão de aplicabilidade para contratos., A aplicabilidade pode variar por capability., A aplicabilidade possui justificativa., A aplicabilidade possui data de validação.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[7.2 Matriz ente × fonte × capability] Cada ente possui decisão de aplicabilidade para editais. · Cada ente possui decisão de aplicabilidade para contratos. · A aplicabilidade pode variar por capabili**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD bf0d1151 differs from origin/main fbc58685 (ahead=97, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (233 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.8067 value={'gate_value': 4, 'unlock_power': 5, 'operational_impact': 5, 'risk_reduction': 3, 'evidence_gain': 4} cost={'effort': 4, 'uncertainty': 3, 'external_dependency': 3, 'change_surface': 3}

### Why unlocked

Open local-stage items in section '7.2 Matriz ente × fonte × capability' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:9e9b0e165ec5 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:fb519704765b ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a524c0b3ccd0 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a04da1ab4a07 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:34174823e54a ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:59661d935e79` only
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

| Field | Value |
|-------|-------|
| **Reviewer** | Quinn (@qa) — independent |
| **Date** | 2026-07-18 |
| **Verdict** | **CONCERNS** |
| **Evidence** | `docs/ops/session-2026-07-18-applicability-matrix/QA-VERDICT.md` |
| **Reviewed** | HEAD `bf0d115` + uncommitted matrix module/tests/DoD/evidence |

### Summary

- pytest `tests/test_applicability_matrix.py`: **4 passed**
- CLI matrix `--limit-entities 20`: **gate.zero_necessary_unknowns=true**, `min_source_combination` present
- All decisions carry `justification`, `validated_at`, `decision_source`
- DoD §7.2 **first 8** structurally proven; items 9–14 correctly remain open
- Residual: CSV universe lacks `esfera` (defaults municipal) → sphere-sensitive complementary rules can mis-decide for estadual/federal `entity_type`s
- Process residual: Done/po_closed/DoD `[x]` preceded this independent review

### Gate decision

**CONCERNS** — first 8 acceptable with documented residuals; not FAIL.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | Quinn (@qa) | Independent review → **CONCERNS**; QA Results + `QA-VERDICT.md` |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
