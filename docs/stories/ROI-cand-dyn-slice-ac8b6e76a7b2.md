# Story: [25. Verdade, linguagem e claims permitidos] 

**Story ID:** `ROI-cand-dyn-slice-ac8b6e76a7b2`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Ready  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-19T082125Z`)  
**Candidate ID:** `cand-dyn-slice:ac8b6e76a7b2`  
**ROI:** `4.3448`  
**DoD refs:** 25. Verdade, linguagem e claims permitidos — itens `PARTIAL` e `BLOCKED` semantics  

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[25. Verdade, linguagem e claims permitidos] **,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 1 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD d022012b differs from origin/main dbc5adb2 (ahead=22, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (262 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 1 open DoD items; ROI biased by section heuristics

**Score:** ROI=4.3448 value={'gate_value': 5, 'unlock_power': 3, 'operational_impact': 2, 'risk_reduction': 5, 'evidence_gain': 4} cost={'effort': 2, 'uncertainty': 1, 'external_dependency': 1, 'change_surface': 1}

### Why unlocked

Open local-stage items in section '25. Verdade, linguagem e claims permitidos' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:cb906bb58392 ROI=2.9241 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:b84aad7b10ee ROI=2.9241 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a94b7d79e0a0 ROI=2.7848 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a60989a8e60e ROI=2.5 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:5068b4058697 ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:ac8b6e76a7b2` only
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

1. **Given** empty/open §25 items for readiness labels, **When** slice delivered, **Then** `PARTIAL_SEMANTICS` exists in `coverage_contract.py`, exported by `validate_indicator_catalog`, and unit-tested
2. **Given** open item "`BLOCKED` significa…", **When** slice delivered, **Then** `BLOCKED_SEMANTICS` is unit-tested and catalog-exported with external/technical dependency wording
3. **Given** evidence + tests green, **When** PO/QA accept, **Then** the two DoD checkboxes are flipped with paths to evidence (no NOT_APPLICABLE inflation)
4. **Given** campaign truth gate, **When** reporting, **Then** PARTIAL never equates READY and never claims campaign DONE

---

## Test commands

- `python3 -m pytest tests/test_indicator_catalog.py -q --tb=short`

---

## Files (planned / delivered)

- `scripts/coverage/coverage_contract.py` — `PARTIAL_SEMANTICS` + catalog export
- `tests/test_indicator_catalog.py` — partial/blocked semantics tests
- `DOD.md` — §25 PARTIAL + BLOCKED
- `docs/ops/session-2026-07-19-partial-blocked-semantics/evidence.json`

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
