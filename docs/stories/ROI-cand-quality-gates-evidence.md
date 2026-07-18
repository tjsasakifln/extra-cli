# Story: Evidência §13.4: ruff/mypy/bandit/pre-commit/CI fail-closed no caminho crítico

**Story ID:** `ROI-cand-quality-gates-evidence`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** InReview  
**Risk level:** **STANDARD**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T233745Z`)  
**Candidate ID:** `cand-quality-gates-evidence`  
**ROI:** `3.3448`  
**DoD refs:** §13.4 Qualidade mínima

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Evidência §13.4: ruff/mypy/bandit/pre-commit/CI fail-closed no caminho crítico**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Cheap evidence_gain for quality DoD checkboxes.

### Evidence of problem

['Current HEAD f8ecad41 differs from origin/main 4da296eb (ahead=16, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Cheap evidence_gain for quality DoD checkboxes.

**Score:** ROI=3.3448 value={'gate_value': 3, 'unlock_power': 2, 'operational_impact': 1, 'risk_reduction': 4, 'evidence_gain': 5} cost={'effort': 2, 'uncertainty': 1, 'external_dependency': 1, 'change_surface': 1}

### Why unlocked

Tooling already in repo; needs re-run evidence pack

### Alternatives discarded

- cand-coverage-m2-multisource-artifacts ROI=2.3565 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-local-backup-restore-proof ROI=2.2308 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-quality-gates-evidence` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** ruff/bandit/pre-commit status recorded with exit codes
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** CI fail-closed (no continue-on-error) re-verified
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Only mark DoD items with real command evidence

---

## Test commands

- `ruff check scripts/ --select E`
- `bandit -q -r scripts/ -ll || true`

---

## Files (planned)

- `docs/ops/session-*/quality-gates/`
- `DOD.md`

---

## Risks

- Lint debt noise

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
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
