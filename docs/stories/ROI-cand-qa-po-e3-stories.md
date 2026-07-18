# Story: QA/PO independentes fecham E3.S1/E3.S2 (InReview → Done) sem inflar selos

**Story ID:** `ROI-cand-qa-po-e3-stories`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T221240Z`)  
**Candidate ID:** `cand-qa-po-e3-stories`  
**ROI:** `3.8448`  
**DoD refs:** §44.4 claim 5 stories InReview, story lifecycle

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **QA/PO independentes fecham E3.S1/E3.S2 (InReview → Done) sem inflar selos**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Barato, reduz risco de story Done sem prova, e é pré-condição citada para PRE_VPS_FINAL_READY.

### Evidence of problem

['Current HEAD 8279381f differs from origin/main 4da296eb (ahead=4, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)']

### Value / ROI justification

Barato, reduz risco de story Done sem prova, e é pré-condição citada para PRE_VPS_FINAL_READY.

**Score:** ROI=3.8448 value={'gate_value': 4, 'unlock_power': 3, 'operational_impact': 2, 'risk_reduction': 4, 'evidence_gain': 4} cost={'effort': 2, 'uncertainty': 1, 'external_dependency': 1, 'change_surface': 1}

### Why unlocked

Não depende de VPS; processo local AIOX; stories existem

### Alternatives discarded

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

- Work defined by candidate `cand-qa-po-e3-stories` only
- Tests and evidence required by acceptance criteria
- AIOX state transitions honored
- Evidence package + state materialization for B2G-E3.S1 / B2G-E3.S2 (InReview, qa_verdict PENDING)

### OUT

- Any lower-ROI unlocked item (must wait for next cycle)
- Blocked external work unless this card is exactly that and resources exist
- Scope expansion / architecture tourism without DoD link
- Portal publico, multi-tenant, billing, K8s/Kafka/Redis/ES without demonstrated need
- Physical works tracking / auto-protocol without human action
- Implementer self-QA of E3.S1/S2 or seal promotion
- Marking E3.S1/S2 Done from @dev

---

## Acceptance Criteria

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** QA gate file with PASS/CONCERNS/FAIL
2. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** PO close only after acceptable verdict
3. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** No READY seal changes beyond authorized claims

---

## Test commands

- `review story gates`
- `pytest resilience subset if code claimed`
- Story E3.S1: `pytest tests/ -k "pncp and (429 or rate_limit or fail_closed or FetchResult)" -v`
- Story E3.S2: `pytest tests/ -k "checkpoint or resume or dlq" -v`
- Focused no-DB (recommended): see handoff `squads/extra-dod-roi/state/handoffs/cyc-2026-07-17T221240Z-dev-to-qa.md`

---

## Files (planned)

- `docs/stories/*`
- `.aiox/state/stories/*`

---

## Risks

- Self-approval se implementador atuar como único QA

## Dependencies

- story files for E3.S1/S2 or epic-pre-vps-truth

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
- [x] Tests/lint per risk level (focused no-DB evidence PASS; broad residual documented for independent QA)
- [x] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer) — ROI process **PASS**; E3.S1/S2 product **CONCERNS**
- [x] @po closed — 2026-07-17 Pax; E3.S1/S2 Done with CONCERNS accepted; no READY seals
- [ ] @devops draft PR / publish path (no auto-merge)
- [x] DoD.md checkboxes only if evidence authorizes — **no READY seal promotion** (LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY remain NOT_READY)

---

## File List

| Path | Action | Notes |
|------|--------|-------|
| `docs/stories/ROI-cand-qa-po-e3-stories.md` | update | Status Ready→InProgress→InReview; DoD checkboxes @dev |
| `.aiox/state/stories/ROI-cand-qa-po-e3-stories.json` | update | status InReview; gates.tests PASS |
| `.aiox/state/stories/B2G-E3.S1.json` | create | InReview, qa_verdict PENDING, HIGH-RISK |
| `.aiox/state/stories/B2G-E3.S2.json` | create | InReview, qa_verdict PENDING, STANDARD |
| `squads/extra-dod-roi/state/handoffs/cyc-2026-07-17T221240Z-dev-to-qa.md` | create | Independent QA package |
| `squads/extra-dod-roi/state/cycles/current.json` | update | IMPLEMENTING → IN_REVIEW |
| `squads/extra-dod-roi/state/cycles/cyc-2026-07-17T221240Z.json` | update | phase log |

**Not modified:** `DOD.md` READY seals; E3.S1/S2 story markdown Status left InReview (not Done); product code.

---

## Dev Agent Record

### Branch

`extra-roi/cand-qa-po-e3-stories` from `origin/main@4da296e`

### Evidence (2026-07-17)

| Suite | Result |
|-------|--------|
| Broad S1 `-k` | 2 passed, 2 failed (chaos fixture drift) |
| Broad S2 `-k` | 97 passed, 5 skipped, 2 failed (chaos + opportunity DB) |
| Focused S1 | **24 passed** |
| Focused S2 | **49 passed** |
| `tests/test_fetch_result.py` | **7 passed** |

Log: `/tmp/grok-goal-00184141f517/implementer/extra-roi-tests-cand-qa-po-e3-stories.log`

### Explicit non-actions

- Did **not** set E3.S1/S2 `qa_verdict` to PASS
- Did **not** mark E3.S1/S2 Done
- Did **not** edit DOD.md READY seals
- Did **not** push/PR

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-17 | @po (Pax) | Validated GO (9/10) v0.1.0 — Status: Draft → Ready; po_validated=true; targets B2G-E3.S1/S2 InReview confirmed; seal inflation forbidden |
| 2026-07-17 | @dev (Dex) | Status Ready → InProgress → InReview. Evidence pack + B2G-E3.S1/S2 state materialization; handoff to independent QA; no seal promotion; E3 qa_verdict left PENDING |
| 2026-07-17 | Quinn (QA) | Independent QA: E3.S1 CONCERNS, E3.S2 CONCERNS, ROI process PASS. No READY seals. Gates written. Cycle → QA. Status stays InReview for @po close. |
| 2026-07-17 | Pax (@po) | **PO close** — accepted ROI PASS + E3.S1/S2 CONCERNS. Status InReview → **Done**. po_closed=true; publication_authorized=true (gates.tests PASS). E3.S1+E3.S2 closed Done. No seal inflation. Follow-ups FU-E3-CHAOS-RESILIENCECONFIG + FU-E3-OPPORTUNITY-DB-MARK. [closure-key: ROI-cand-qa-po-e3-stories:commit:a12190c8fca1af0c564de682d1dbc0f9d755e116] |

---

## QA Results

**Reviewer:** Quinn (@qa / adversarial-qa-auditor)  
**Independent:** true  
**Date:** 2026-07-17  
**Verdict (ROI process):** **PASS**  
**Reviewed commit:** `a12190c8fca1af0c564de682d1dbc0f9d755e116`  
**Gate file:** `squads/extra-dod-roi/state/qa/cyc-2026-07-17T221240Z-qa.json`

### Product story gates

| Story | Verdict | Gate |
|-------|---------|------|
| B2G-E3.S1 | **CONCERNS** | `squads/extra-dod-roi/state/qa/B2G-E3.S1-qa.json` |
| B2G-E3.S2 | **CONCERNS** | `squads/extra-dod-roi/state/qa/B2G-E3.S2-qa.json` |

### Process checks

| Check | Result |
|-------|--------|
| Independent gate files exist for E3.S1 + E3.S2 | PASS |
| No READY seal changes (DOD.md untouched) | PASS |
| Self-approval avoided (implementer ≠ QA) | PASS |
| E3 Status not Done; po_closed=false | PASS |
| Focused suites re-run by QA | PASS (24 + 49) |

### Residual

Chaos `ResilienceConfig` fixture drift + opportunity DB integration noise documented as CONCERNS on product stories — non-blocking for PO close (ACs met).

### PO Close Acknowledgement

**PO:** Pax (@po)  
**Date:** 2026-07-17  
**ROI process verdict accepted:** PASS  
**Product verdicts accepted:** B2G-E3.S1=CONCERNS, B2G-E3.S2=CONCERNS  
**AC1–3:** satisfied (independent gates exist; PO close after acceptable verdict; no unauthorized READY seals)  
**Closed targets:** B2G-E3.S1 Done, B2G-E3.S2 Done, this ROI story Done  
**publication_authorized:** true (qa_verdict=PASS, gates.tests=PASS, po_closed=true)  
**DOD.md:** not modified — LOCAL_RESILIENCE_READY and PRE_VPS_FINAL_READY remain NOT_READY  

**Follow-ups (owner + note):**

| ID | Owner | Note |
|----|-------|------|
| `FU-E3-CHAOS-RESILIENCECONFIG` | @dev | Fix `tests/chaos/test_429_rate_limit.py` `_cfg` for required `ResilienceConfig` fields (or `for_tests`/`from_env`) |
| `FU-E3-OPPORTUNITY-DB-MARK` | @dev | Mark/exclude opportunity integration tests from default no-DB `-k` smoke |

**Next:** @devops draft PR / publish path (no auto-merge). No seal promotion.

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
