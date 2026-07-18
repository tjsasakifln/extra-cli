# Story: [Atualização comprovada — ciclo B2G operacional de ] Suíte global completa verde. O workflow marcou `Test All (fu · Freshness coverage mensurável por entidade dentro dos SLAs.

**Story ID:** `ROI-cand-dyn-slice-a53bdc0173af`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** InReview  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T164226Z`)  
**Candidate ID:** `cand-dyn-slice:a53bdc0173af`  
**ROI:** `1.2261`  
**DoD refs:** Atualização comprovada — ciclo B2G operacional de 17/07/2026, Suíte global completa verde. O workflow marcou `Test All (full suite)` como `ski, Freshness coverage mensurável por entidade dentro dos SLAs.  
**PO validated:** 2026-07-18 by @po (Pax) — GO with sharpened ACs

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[Atualização comprovada — ciclo B2G operacional de ] Suíte global completa verde. O workflow marcou `Test All (fu · Freshness coverage mensurável por entidade dentro dos SLAs.**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 2 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 311e8ea3 differs from origin/main fbc58685 (ahead=107, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (235 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 2 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.2261 value={'gate_value': 2, 'unlock_power': 2, 'operational_impact': 2, 'risk_reduction': 2, 'evidence_gain': 3} cost={'effort': 3, 'uncertainty': 3, 'external_dependency': 2, 'change_surface': 2}

### Why unlocked

Open local-stage items in section 'Atualização comprovada — ciclo B2G operacional de 17/07/2026' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:b8d41f43fbfc ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:b3ea2a2669e1 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:2b83aa82a369 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:dd7b4910d7f9 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:a6cf12911b22 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:a53bdc0173af` only
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

### AC1 — Suíte global (`dod:b06848ca7f90`)

1. **Given** local Postgres `extra_test` on 5433 and project deps, **When** implementer re-runs critical readiness + full-suite collect/marker inventory, **Then** evidence pack under `docs/ops/session-2026-07-18-suite-freshness/` records exit codes, pass/fail/skip counts, and residual schema/debt reasons.
2. **Given** that inventory, **When** any skip is remaining, **Then** it is **not** converted to pass; item stays `[ ]` unless full suite (or documented CI path) is actually green with exit 0 and zero unjustified skips.
3. **Given** prior pack `session-2026-07-17-full-suite-debt`, **When** this slice completes, **Then** either residual debt is reduced with tests OR the item is left open with refreshed honest MANIFEST — never flipped by documentation alone.

### AC2 — Freshness coverage por entidade (`dod:925f2c0e059a`)

1. **Given** DSN to real PostgreSQL, **When** operator runs entity freshness coverage CLI/report, **Then** JSON+CSV are produced with: denominator (universo ativo raio), numerator (entidades com `last_seen`/`observed_at` dentro do SLA), % , SLA hours, and **nominal gap list** (entity_id + last_seen + status).
2. **Given** empty/stale data, **When** the same command runs, **Then** overall may be FAIL/NOT_READY but measurement still succeeds (exit 0 for measure mode or explicit fail-closed exit 2 with structured report — documented).
3. **Given** unit/integration tests for the reporter, **When** pytest scoped to new tests runs, **Then** exit 0.
4. **Given** aggregate-only source-level freshness, **When** QA inspects the report, **Then** it proves **entity-level** rollup (not only `freshness-gate.json` source-level).

### AC3 — Process integrity

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** each of 2 `dod_item_ids` is proven with evidence or left open honestly.
2. **Given** campaign rules, **When** closing, **Then** no `NOT_APPLICABLE` is used to hit campaign meta.
3. **Given** independent `@qa` / `adversarial-qa-auditor` ≠ implementer, **When** any DoD `[x]` flip is proposed, **Then** QA verdict is PASS|CONCERNS first; implementer never touches DoD checkboxes.

---

## Test commands

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m pytest tests/ -q --tb=line -k "freshness_entity or entity_freshness or suite_freshness" --tb=no
python3 -m scripts.<entity_freshness_module> --dsn "$LOCAL_DATALAKE_DSN" --output docs/ops/session-2026-07-18-suite-freshness/
# full suite inventory (may be non-zero; record honestly)
python3 -m pytest tests/ --collect-only -q 2>&1 | tee docs/ops/session-2026-07-18-suite-freshness/collect.txt
```

---

## Files (planned)

- `scripts/` (entity freshness reporter or extension of coverage_contract / freshness_gate)
- `tests/` (unit + optional PG integration)
- `docs/ops/session-2026-07-18-suite-freshness/` (evidence pack)
- `docs/stories/ROI-cand-dyn-slice-a53bdc0173af.md` / `.aiox/state/stories/...`
- `DOD.md` — **only after independent QA**, and only for items actually proven

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
- [x] Tests/lint per risk level
- [ ] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer)
- [ ] @po closed
- [ ] @devops draft PR / publish path (no auto-merge)
- [ ] DoD.md checkboxes only if evidence authorizes

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | @po (Pax) | GO → Ready; sharpened AC for suite inventory + entity-level freshness; forbid false full-suite green |
| 2026-07-18 | delivery-engineer | entity_freshness CLI + tests + evidence pack; suite inventory leave-open; handoff to QA |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
