# Story: Pós-merge PR #12: revalidar offline gate na main e impedir restauração de selos READY sem live proof

**Story ID:** `ROI-cand-post-merge-truth-gate-honesty`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Draft  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T214622Z`)  
**Candidate ID:** `cand-post-merge-truth-gate-honesty`  
**ROI:** `5.1522`  
**DoD refs:** §44 NOT_READY, PRE_VPS_FINAL_READY still blocked, no false green

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Pós-merge PR #12: revalidar offline gate na main e impedir restauração de selos READY sem live proof**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Barato e crítico após merge: garantir que main não promoveu PRE_VPS_FINAL_READY; base limpa para live canary humano.

### Evidence of problem

['PR #12 truth-gate appears MERGED into main (no open PR #12; truth docs present). Offline gate may be on main — still NOT PRE_VPS_FINAL_READY without live canary + PG evidence.', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)']

### Value / ROI justification

Barato e crítico após merge: garantir que main não promoveu PRE_VPS_FINAL_READY; base limpa para live canary humano.

**Score:** ROI=5.1522 value={'gate_value': 4, 'unlock_power': 3, 'operational_impact': 2, 'risk_reduction': 5, 'evidence_gain': 4} cost={'effort': 1, 'uncertainty': 1, 'external_dependency': 1, 'change_surface': 1}

### Why unlocked

PR #12 merged; residual work is verify main still honest and offline gate green

### Alternatives discarded

- cand-qa-po-e3-stories ROI=3.8448 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-workspace-daily-evidence-pack ROI=2.2805 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-full-suite-schema-debt ROI=1.8571 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-coverage-slice-pending-collection ROI=1.62 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-golden-path-pncp-health ROI=1.3617 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-post-merge-truth-gate-honesty` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** make pre-vps-final-gate-offline green on main
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** DOD/docs still forbid LOCAL_RESILIENCE_READY and PRE_VPS_FINAL_READY without live proof
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** No new false-green health path introduced

---

## Test commands

- `make pre-vps-final-gate-offline`
- `python3 -m scripts.ops.health --env development; test exit != 0 without live evidence`

---

## Files (planned)

- `docs/operations/* only if residual drift`
- `no product rewrite`

---

## Risks

- Narrativa de merge confundida com readiness live

## Dependencies

- main contains truth-gate commits

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
