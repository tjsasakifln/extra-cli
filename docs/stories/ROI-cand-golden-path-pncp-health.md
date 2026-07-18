# Story: Estabilizar golden path PNCP (timeout) e source health observável

**Story ID:** `ROI-cand-golden-path-pncp-health`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **STANDARD**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T231812Z`)  
**Candidate ID:** `cand-golden-path-pncp-health`  
**ROI:** `1.3617`  
**DoD refs:** golden path PNCP falhou por timeout, source health

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Estabilizar golden path PNCP (timeout) e source health observável**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Utilidade diária e saúde de fonte; external_dependency alta limita ROI vs truth-gate/QA.

### Evidence of problem

['Current HEAD 02a9224e differs from origin/main 4da296eb (ahead=8, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO']

### Value / ROI justification

Utilidade diária e saúde de fonte; external_dependency alta limita ROI vs truth-gate/QA.

**Score:** ROI=1.3617 value={'gate_value': 2, 'unlock_power': 3, 'operational_impact': 4, 'risk_reduction': 3, 'evidence_gain': 3} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 4, 'change_surface': 2}

### Why unlocked

Code/ops local; improves daily utility and evidence

### Alternatives discarded

- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-golden-path-pncp-health` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Reproducible golden path result recorded (pass or honest degraded health)
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** No success claim on timeout

---

## Test commands

- `make golden-path-quick`
- `python scripts/golden_path.py --help`

---

## Files (planned)

- `scripts/golden_path.py`
- `scripts/crawl/*`
- `scripts/ops/*`

---

## Risks

- PNCP rate limits
- flaky network

## Dependencies

- resilience adapters

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
**Date:** 2026-07-17T23:22:30Z  
**Reviewed commit:** `7231be774515426c980ce1061863e03f0a74db59`  
**Cycle:** `cyc-2026-07-17T231812Z`  
**Verdict:** **PASS**

### Independent re-verification

| Check | Result |
|-------|--------|
| Session `MANIFEST.md` + `02-run.exit` | **GOLDEN_EXIT=1**; honest degraded documented |
| `python3 scripts/golden_path.py --skip-freshness --skip-reports` | **exit 1** (PG unavailable; `fe_sendauth` / NAO respondeu) |
| Latest ledger status | **failed** (`gp-20260717-202044`, `db_connectivity=fail`) |
| `slice-result.json` | `claim_success=false`, `FAIL_CLOSED_DB_UNAVAILABLE` |
| `pytest -o addopts='' -q tests/ -k golden_path` | **14 passed** |
| Full green / PRE_VPS / live PNCP OK claims | **none** |

### AC

| AC | Verdict |
|----|---------|
| AC1 Reproducible golden path (pass or honest degraded) | **PASS** — exit 1 + ledger failed reproducible without PG |
| AC2 No success claim on timeout/DB fail | **PASS** — fail-closed return 1; no success claim in canonical evidence |

### Residual concerns

1. **low** — `01-run.exit` has `GOLDEN_EXIT=0` while log shows DB fail; superseded by `02-run.exit=1` + independent re-run.
2. **low** — Commit is evidence-pack only (no `scripts/golden_path.py` delta); behavior already present.
3. **medium** — Live PNCP source health still not proven (needs PG + network); do not rebrand as operational green.

### Gate

**PASS** → next `@po` close (cycle phase QA → PO_CLOSE). Honest fail-closed is a valid AC outcome.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-17 | adversarial-qa-auditor (@qa) | Independent QA PASS; reviewed_commit 7231be7; InReview→Done |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
