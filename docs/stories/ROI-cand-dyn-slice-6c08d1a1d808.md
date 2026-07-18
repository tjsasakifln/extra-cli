# Story: [7.1 Registry de fontes] Existe registry canônico de fontes. · Cada fonte possui identificador estável. · Cada fonte possui URL ou endpoint canônico. (+5 more)

**Story ID:** `ROI-cand-dyn-slice-6c08d1a1d808`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T155411Z`)  
**Candidate ID:** `cand-dyn-slice:6c08d1a1d808`  
**ROI:** `1.8067`  
**DoD refs:** 7.1 Registry de fontes, Existe registry canônico de fontes., Cada fonte possui identificador estável., Cada fonte possui URL ou endpoint canônico., Cada fonte informa capacidades suportadas., Cada fonte informa cobertura geográfica.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[7.1 Registry de fontes] Existe registry canônico de fontes. · Cada fonte possui identificador estável. · Cada fonte possui URL ou endpoint canônico. (+5 more)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD e82f5f2e differs from origin/main fbc58685 (ahead=95, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (234 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 8 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.8067 value={'gate_value': 4, 'unlock_power': 5, 'operational_impact': 5, 'risk_reduction': 3, 'evidence_gain': 4} cost={'effort': 4, 'uncertainty': 3, 'external_dependency': 3, 'change_surface': 3}

### Why unlocked

Open local-stage items in section '7.1 Registry de fontes' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:d8deaa518e86 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:687b22d210fe ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:59661d935e79 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:9e9b0e165ec5 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:fb519704765b ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:6c08d1a1d808` only
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

**Reviewer:** Quinn (@qa)  
**Date:** 2026-07-18  
**Scope:** DoD §7.1 first 8 items only  
**Verdict:** **CONCERNS**

### Evidence re-run

- `python3 -m scripts.crawl.registry --validate --json` → `ok=true`, 11 sources, 3 active, 8 `implemented_not_proven`
- `python3 -m pytest tests/test_source_registry_dod71.py -q --no-cov -o addopts=` → **5 passed**
- Full write-up: `docs/ops/session-2026-07-18-source-registry-7-1/QA-VERDICT.md`

### Per-item (first 8)

| # | Item | Status |
|---|------|--------|
| 1 | Registry canônico | DONE |
| 2 | Identificador estável | DONE |
| 3 | URL/endpoint canônico | PARTIAL (`transparencia` pseudo-URL) |
| 4 | Capacidades | DONE |
| 5 | Cobertura geográfica | DONE |
| 6 | Necessidade de credenciais | DONE |
| 7 | Limites de paginação | DONE (primaries non-unknown; complementary residual) |
| 8 | Rate limits | DONE (primaries non-unknown; complementary residual) |

### Falsification

- Active without URL → held (impossible via `operational_status`)
- Empty capabilities → none present
- Module/crawler without `operational_validated` as active → held (`implemented_not_proven`)

### Residual (non-blocking)

1. `transparencia.canonical_url` is not a fetchable endpoint
2. Complementary sources still `unknown` pagination/rate
3. Negative unit tests for falsify probes not yet automated
4. Process: state had orchestrator `PASS` before independent `QA-VERDICT.md` — this section is the independent record

**Gate:** CONCERNS — first 8 substantively met; residuals documented. Not FAIL.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | Quinn (@qa) | Independent QA on §7.1 first 8 → **CONCERNS**; wrote session QA-VERDICT.md |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
