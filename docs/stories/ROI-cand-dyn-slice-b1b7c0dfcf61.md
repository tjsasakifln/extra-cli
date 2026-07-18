# Story: [14. Backup e recuperação local] O restore recompõe o universo-alvo. · PDFs e anexos não são armazenados no PostgreSQL sem justific · Metadados de arquivos incluem hash, tamanho, tipo e origem. (+1 mo

**Story ID:** `ROI-cand-dyn-slice-b1b7c0dfcf61`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T134428Z`)  
**Candidate ID:** `cand-dyn-slice:b1b7c0dfcf61`  
**ROI:** `2.5`  
**DoD refs:** 14. Backup e recuperação local, O restore recompõe o universo-alvo., PDFs e anexos não são armazenados no PostgreSQL sem justificativa., Metadados de arquivos incluem hash, tamanho, tipo e origem., Um teste de restauração real está registrado antes de fechar o estágio local.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[14. Backup e recuperação local] O restore recompõe o universo-alvo. · PDFs e anexos não são armazenados no PostgreSQL sem justific · Metadados de arquivos incluem hash, tamanho, tipo e origem. (+1 mo**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 4 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 6a06d5b7 differs from origin/main fbc58685 (ahead=32, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (251 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 4 open DoD items; ROI biased by section heuristics

**Score:** ROI=2.5 value={'gate_value': 4, 'unlock_power': 3, 'operational_impact': 3, 'risk_reduction': 5, 'evidence_gain': 5} cost={'effort': 3, 'uncertainty': 2, 'external_dependency': 2, 'change_surface': 2}

### Why unlocked

Open local-stage items in section '14. Backup e recuperação local' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:5068b4058697 ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:6a6725b134cb ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:8e8eb18e2c5f ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:eba1cdc41d81 ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:848d772e0c1c ROI=2.4928 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:b1b7c0dfcf61` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Each of 4 dod_item_ids proven with evidence or left open
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
| 2026-07-18 | @po | Ready |
| 2026-07-18 | @qa/@po | PASS |
