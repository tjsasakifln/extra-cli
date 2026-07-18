# Story: [27. Organização e manutenção do código] Mudanças de métrica exigem atualização da definição. · Código legado possui plano de remoção. · TODOs críticos possuem issue ou story. (+4 more)

**Story ID:** `ROI-cand-dyn-slice-e845e4e64aba`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T163513Z`)  
**Candidate ID:** `cand-dyn-slice:e845e4e64aba`  
**ROI:** `1.6535`  
**DoD refs:** 27. Organização e manutenção do código, Mudanças de métrica exigem atualização da definição., Código legado possui plano de remoção., TODOs críticos possuem issue ou story., Comentários não contradizem o código., Scripts operacionais suportam `--dry-run` quando aplicável.

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **[27. Organização e manutenção do código] Mudanças de métrica exigem atualização da definição. · Código legado possui plano de remoção. · TODOs críticos possuem issue ou story. (+4 more)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Dynamic slice of 7 open DoD items; ROI biased by section heuristics

### Evidence of problem

['Current HEAD 7386de18 differs from origin/main fbc58685 (ahead=106, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'Dynamic DOD generation produced 40 section slices (238 open items covered)', 'Candidate cand-qa-po-e3-stories marked COMPLETED: B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)', 'Candidate cand-full-suite-schema-debt marked COMPLETED: ROI-cand-full-suite-schema-debt Done with QA PASS + PO close', 'Candidate cand-coverage-slice-pending-collection marked COMPLETED: ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)', 'Candidate cand-coverage-scale-m2-more-entities marked COMPLETED: ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close', 'Candidate cand-dod-unit-test-evidence-pack marked COMPLETED: ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close', 'Candidate cand-workspace-daily-evidence-pack marked COMPLETED: ROI-cand-workspace-daily-evidence-pack Done with QA/PO', 'Candidate cand-golden-path-pncp-health marked COMPLETED: ROI-cand-golden-path-pncp-health Done with QA PASS + PO close']

### Value / ROI justification

Dynamic slice of 7 open DoD items; ROI biased by section heuristics

**Score:** ROI=1.6535 value={'gate_value': 2, 'unlock_power': 2, 'operational_impact': 3, 'risk_reduction': 3, 'evidence_gain': 3} cost={'effort': 3, 'uncertainty': 2, 'external_dependency': 1, 'change_surface': 3}

### Why unlocked

Open local-stage items in section '27. Organização e manutenção do código' without VPS/live/human-accept blocker patterns

### Alternatives discarded

- cand-dyn-slice:a53bdc0173af ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:b8d41f43fbfc ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:b3ea2a2669e1 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:2b83aa82a369 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-dyn-slice:dd7b4910d7f9 ROI=1.2261 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-dyn-slice:e845e4e64aba` only
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

1. **Given** the current mainline and DoD constraints, **When** this slice is delivered, **Then** Each of 7 dod_item_ids proven with evidence or left open
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

**Reviewer:** Quinn (@qa) — independent  
**Date:** 2026-07-18  
**Verdict:** **CONCERNS**

Full report: [`docs/ops/session-2026-07-18-code-hygiene/QA-VERDICT.md`](../ops/session-2026-07-18-code-hygiene/QA-VERDICT.md)

### Per-item (DoD §27)

| Item | Status |
|------|--------|
| Metric definition policy + catalog | DONE |
| Legacy removal plan | DONE |
| Critical TODOs tracked (FIXME untracked=0) | DONE |
| Comments vs code (heuristic) | DONE |
| Operational `--dry-run` | DONE |
| Destructive confirm + rollback | DONE (primary `golden_clean_env`); residual soft-checks on 2 scripts |
| Logs ≠ error handling (fail-closed) | PARTIAL |

### Re-run evidence

- `pytest tests/test_code_hygiene_gate.py` → 3 passed  
- `code_hygiene_gate --json` → `summary.ok=true`  
- `golden_clean_env --dry-run` → exit 0  
- `golden_clean_env` without confirm → REFUSE exit 3  

### Residual concerns

- C1: destructive inventory soft-pass for `backup-database.sh` / `local_backup_restore_proof.py`  
- C2: TODO scan limited to `scripts/**/*.py`  
- C3: logs_vs_errors intentionally PARTIAL  

**Falsify:** zero-TODO claim is false (`n_todo_like=4`); dry-run present on inventory; DROP without confirm refused.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | Quinn (@qa) | Independent QA CONCERNS; QA Results + session QA-VERDICT.md |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
