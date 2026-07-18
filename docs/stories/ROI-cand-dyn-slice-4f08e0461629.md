# Story: [12.1 Golden path local] O golden path gera relatório de editais. · O golden path gera relatório de contratos. · O golden path gera relatório de concorrentes. (+3 more)

**Story ID:** `ROI-cand-dyn-slice-4f08e0461629`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T151824Z`)  
**Candidate ID:** `cand-dyn-slice:4f08e0461629`  
**ROI:** `1.968`  
**DoD refs:** 12.1 Golden path local, O golden path gera relatório de editais., O golden path gera relatório de contratos., O golden path gera relatório de concorrentes., O golden path gera relatório de referências de valores., O golden path gera PDF.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[12.1 Golden path local] O golden path gera relatório de editais. · O golden path gera relatório de contratos. · O golden path gera relatório de concorrentes. (+3 more)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 6 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD c55c9058 differs from origin/main fbc58685 (ahead=84, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (231 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 6 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.968 value={'gate_value': 4, 'unlock_power': 4, 'operational_impact': 4, 'risk_reduction': 3, 'evidence_gain': 4} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 2, 'change_surface': 3}

### Why unlocked

Open local-stage items in section '12.1 Golden path local' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:b50513eeb753 ROI=1.9615 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:19ce6ecf8869 ROI=1.9615 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:d58f00f868f0 ROI=1.9615 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:5c9270b0129a ROI=1.9615 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:6c08d1a1d808 ROI=1.8067 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:4f08e0461629` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Each of 6 dod_item_ids proven with evidence or left open
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
- [x] Tests/lint per risk level (pytest `tests/test_golden_path_pack.py` 2 passed; independent QA re-run)
- [x] @qa independent verdict PASS (adversarial-qa-auditor; not implementer) — artifact `cyc-2026-07-18T151824Z-qa.json`
- [ ] @po closed
- [ ] @devops draft PR / publish path (no auto-merge)
- [ ] DoD.md checkboxes only if evidence authorizes (pending @po flip of authorized list only)

---

## QA Results

**Reviewer:** Quinn (@qa) / adversarial-qa-auditor  
**Date:** 2026-07-18  
**Verdict:** **PASS**  
**Reviewed commit:** `95a266e7e0ed6068edfc12c2c2d60809c226d7d6`  
**Artifact:** `squads/extra-dod-roi/state/qa/cyc-2026-07-18T151824Z-qa.json`  
**Evidence:** `docs/ops/session-2026-07-18-golden-reports/`

### Summary

Commercial golden-path pack proven: dedicated CSVs for editais (N=8), contratos (N=0 honest empty + limitation), concorrentes (N=6 fallback órgãos + limitation), referências de valores (N=4), and real reportlab PDF (`%PDF-1.4`, size>0). `panorama.py --output-pdf` no longer stubs; `golden_path.run_commercial_pack` sets `status=generated` only when file exists with size>0. **Leave open: ambiente limpo.** Never claim 95% coverage or full competitor market.

### Evidence commands (independent re-run)

| Command | Exit | Result |
|---------|------|--------|
| `pytest tests/test_golden_path_pack.py -q --no-cov` | 0 | 2 passed |
| inspect `pack/evidence-pack/*.pdf` | 0 | exists size=2338 magic `%PDF-1.4` |
| inspect CSVs editais/contratos/concorrentes/referencias_valores | 0 | 8 / 0 / 6 / 4 rows; contratos empty+limitation |
| inspect `panorama.py` + `panorama-pdf.log` | 0 | stub removed; PDF path under `output/pdfs/` |
| inspect `golden_path.py::run_commercial_pack` | 0 | generated iff file size>0 |

### Authorized DoD flips (exact)

**In-slice (5/6):**
- L909 O golden path gera relatório de editais.
- L910 O golden path gera relatório de contratos.
- L911 O golden path gera relatório de concorrentes.
- L912 O golden path gera relatório de referências de valores.
- L914 O golden path gera PDF.

**Must stay open (1/6):**
- L919 O golden path pode ser executado em ambiente limpo. (used existing `extra_test`)

### AC trace

- AC1: PASS (5 proven + 1 open with justification)
- AC2: PASS (no NOT_APPLICABLE)
- AC3: PASS (independent QA; DoD still `[ ]` for target lines)

### Gate decision

**PASS** — po_closed remains false until @po flips authorized lines and closes. Residual: clean-env; optional header-only empty contratos CSV; concorrentes fallback semantics.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | @po | Ready |
| 2026-07-18 | delivery-engineer | golden_path_pack + real PDF (flip after QA) |
| 2026-07-18 | @qa adversarial | PASS — authorize 5 flips (editais/contratos/concorrentes/refs/PDF); leave open ambiente limpo |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
| 2026-07-18 | @po | Closed QA PASS; flipped 5 report/PDF items; ambiente limpo open |
