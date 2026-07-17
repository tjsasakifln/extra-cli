# Story: Fatia vertical de cobertura operacional: desbloquear pending_collection com proveniência (N entidades, não 95%)

**Story ID:** `ROI-cand-coverage-slice-pending-collection`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T230924Z`)  
**Candidate ID:** `cand-coverage-slice-pending-collection`  
**ROI:** `1.62`  
**DoD refs:** cobertura operacional 0/1093, pending_collection=714, 95% meta

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Fatia vertical de cobertura operacional: desbloquear pending_collection com proveniência (N entidades, não 95%)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Único caminho material para sair de 0% cobertura operacional; ROI alto em impacto operacional mesmo com esforço maior.

### Evidence of problem

['Current HEAD e11a167e differs from origin/main 4da296eb (ahead=4, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO']

### Value / ROI justification

Único caminho material para sair de 0% cobertura operacional; ROI alto em impacto operacional mesmo com esforço maior.

**Score:** ROI=1.62 value={'gate_value': 3, 'unlock_power': 4, 'operational_impact': 5, 'risk_reduction': 3, 'evidence_gain': 4} cost={'effort': 4, 'uncertainty': 3, 'external_dependency': 3, 'change_surface': 3}

### Why unlocked

Registry 1093 existe; pipeline de estágios existe; pode avançar N entidades sem VPS

### Alternatives discarded

- cand-golden-path-pncp-health ROI=1.3617 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-coverage-slice-pending-collection` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** N>0 entities advanced in operational stages with run_id/raw/sha
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Report does not claim 95%
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** commercial_signal remains separate metric

---

## Test commands

- `pytest tests/ -k coverage -q`
- `python -m scripts workspace coverage (or project equivalent)`

---

## Files (planned)

- `scripts/coverage/*`
- `scripts/source_registry/*`
- `output/coverage/`

---

## Risks

- Confundir sinal comercial (116) com cobertura operacional
- Dependência de fontes externas rate-limit

## Dependencies

- source registry sync
- coverage contract multi-metric

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
**Date:** 2026-07-17T23:20:00Z  
**Reviewed commit:** `451ba028fe4fcb3469bc0fc10772177afd043741`  
**Cycle:** `cyc-2026-07-17T230924Z`  
**Verdict:** **PASS**

### Independent re-verification

| Check | Result |
|-------|--------|
| `pytest -o addopts='' -q tests/unit/source_registry/test_promote_from_evidence.py` | **6 passed** |
| `load_registry()` + `is_strict_operational` | **5 / 1093** (expect ≥5) |
| Contract report offline regen | **M2 5/1093 (0.46%)**; commercial 116 separate; `headline_is_coverage=false` |
| Provenance SHA vs raw jsonl | **match** `2b737ff8d5a9b166…`; norm_ids present in artifact |
| `claims_95_reached` / MANIFEST 95% | **false / NO** |
| dry_run on promoting evidence | **false** |
| Forbidden seals (LOCAL_RESILIENCE / PRE_VPS / 95%) | **not claimed** |
| DOD.md flip | **none** in commit |

### AC

| AC | Verdict |
|----|---------|
| AC1 N>0 entities with run_id/raw/sha | **PASS** — 5 verified + strict operational; real crawl evidence |
| AC2 Report does not claim 95% | **PASS** — M2=0.46%; explicit non-claim |
| AC3 commercial_signal separate | **PASS** — kind=commercial_signal; not coverage |

### Residual (non-blocking)

- Duplicate promote evidence entries (2× same run_id per entity)
- `use_network=True` even on offline promote path (crawl was live; flag still imprecise)
- Offline `reconciled=True` uses synthetic recon id, not PG entity_coverage
- SLA 24h from last_success — M2 numerator will decay without refresh

**Gate file:** `squads/extra-dod-roi/state/qa/cyc-2026-07-17T230924Z-qa.json`  
**Status:** remains **InReview** until @po close (QA does not set Done / publication).

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-17 | @qa / adversarial-qa-auditor | Independent QA PASS on `451ba02`; gate file written |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
| 2026-07-17 | Pax (@po) | PO close after QA PASS — InReview → Done |
