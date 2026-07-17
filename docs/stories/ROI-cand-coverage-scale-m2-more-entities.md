# Story: Escalar M2 operacional: promover mais entidades com proveniência (sem claim 95%)

**Story ID:** `ROI-cand-coverage-scale-m2-more-entities`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **STANDARD**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T232427Z`)  
**Candidate ID:** `cand-coverage-scale-m2-more-entities`  
**ROI:** `1.8067`  
**DoD refs:** operational_source_coverage < 95%, pending_collection residual

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Escalar M2 operacional: promover mais entidades com proveniência (sem claim 95%)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Material path from 5/1093 toward gate 95% without false green.

### Evidence of problem

['Current HEAD 5dcc7da4 differs from origin/main 4da296eb (ahead=11, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Material path from 5/1093 toward gate 95% without false green.

**Score:** ROI=1.8067 value={'gate_value': 4, 'unlock_power': 5, 'operational_impact': 5, 'risk_reduction': 3, 'evidence_gain': 4} cost={'effort': 4, 'uncertainty': 3, 'external_dependency': 3, 'change_surface': 3}

### Why unlocked

First N-slice landed; still far from 95%; offline+PG paths exist

### Alternatives discarded

- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-coverage-scale-m2-more-entities` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** M2 numerator increases by N>0 vs previous evidence pack
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** No 95% claim unless measured >=95%
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** commercial_signal remains separate

---

## Test commands

- `pytest tests/unit/source_registry/test_promote_from_evidence.py -q`
- `python -m scripts.coverage.coverage_contract_cli report --offline`

---

## Files (planned)

- `scripts/source_registry/acquisition/*`
- `data/entity_source_registry.jsonl`
- `docs/ops/session-*/`

---

## Risks

- Rate limits
- SLA decay on old artifacts

## Dependencies

- cand-coverage-slice provenance machinery

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

**Reviewer:** adversarial-qa-auditor (Quinn) — independent of implementer `delivery-engineer`  
**Date:** 2026-07-17T23:29:17Z  
**Reviewed commit:** `ec407c9ee69a3d9cf6a9d38b1786274b986ce8d3`  
**Cycle:** `cyc-2026-07-17T232427Z`  
**Verdict:** **PASS**

### Independent re-verification

| Check | Result |
|-------|--------|
| `pytest -o addopts='' -q tests/unit/source_registry/test_promote_from_evidence.py` | **6 passed** |
| `load_registry()` + `is_strict_operational` | **81 / 1093** (expect ~81) |
| Session pack (MANIFEST + scale-result + contract-report) | **M2 5→81 (+76); pct=7.41; claims_95=false** |
| Contract commercial vs coverage | **commercial kind=commercial_signal (116); M2 kind=coverage (81); headline_is_coverage=false** |
| `claims_95_reached` / MANIFEST 95% | **false / NO** |
| Forbidden seals (LOCAL_RESILIENCE / PRE_VPS / 95%) | **not claimed** |
| DOD.md flip | **none** in commit |

### AC

| AC | Verdict |
|----|---------|
| AC1 M2 numerator increases by N>0 vs previous (5) | **PASS** — 5 → 81 (+76); independent recount 81 |
| AC2 No 95% claim | **PASS** — 7.41% << 95; explicit non-claim |
| AC3 commercial_signal separate | **PASS** — kind=commercial_signal; not coverage |

### Residual (non-blocking)

- Duplicate pncp source entries on some entities (prior promote path)
- M2 still far from 95% (7.41%) — progress only; SLA decay risk
- Offline synthetic reconcile inherited; not full PG proof

**Gate file:** `squads/extra-dod-roi/state/qa/cyc-2026-07-17T232427Z-qa.json`  
**Status:** remains **InReview** until @po close (QA does not set Done / publication).  
**Next:** `PO_CLOSE`

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-17 | @qa / adversarial-qa-auditor | Independent QA PASS on `ec407c9`; cycle IN_REVIEW→QA; gate file written |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
