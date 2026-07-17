# Story: Pacote de evidência reproduzível do workspace cotidiano (today/opportunities/dossier/coverage)

**Story ID:** `ROI-cand-workspace-daily-evidence-pack`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  
**Risk level:** **STANDARD**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-17T223227Z`)  
**Candidate ID:** `cand-workspace-daily-evidence-pack`  
**ROI:** `2.2805`  
**DoD refs:** workspace cotidiano executa comandos, evidências utilizáveis

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **Pacote de evidência reproduzível do workspace cotidiano (today/opportunities/dossier/coverage)**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

Baixo esforço, alto evidence_gain; não fecha 95% mas fortalece claims permitidos.

### Evidence of problem

['Current HEAD a61dee37 differs from origin/main 4da296eb (ahead=3, behind=0).', 'DoD veto active: Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof', 'Superseded claim: LOCAL_RESILIENCE_READY → NOT_READY (DOD.md §44)', 'Superseded claim: PRE_VPS_FINAL_READY → NOT_READY (DOD.md residual / PR truth gate)', 'E3.S1 and E3.S2 already Done with independent QA/PO — cand-qa-po-e3-stories not UNLOCKED']

### Value / ROI justification

Baixo esforço, alto evidence_gain; não fecha 95% mas fortalece claims permitidos.

**Score:** ROI=2.2805 value={'gate_value': 2, 'unlock_power': 2, 'operational_impact': 4, 'risk_reduction': 2, 'evidence_gain': 5} cost={'effort': 2, 'uncertainty': 2, 'external_dependency': 2, 'change_surface': 1}

### Why unlocked

CLI exists per DoD narrative; needs fresh evidence pack

### Alternatives discarded

- cand-qa-po-e3-stories: COMPLETED — B2G-E3.S1/S2 Done with po_closed + independent QA (S1 qa=CONCERNS, S2 qa=CONCERNS); do not re-bind or re-implement
- cand-full-suite-schema-debt ROI=1.8571 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-coverage-slice-pending-collection ROI=1.62 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-golden-path-pncp-health ROI=1.3617 preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa
- cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida
- blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente
- VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana

---

## Scope

### IN

- Work defined by candidate `cand-workspace-daily-evidence-pack` only
- Tests and evidence required by acceptance criteria
- AIOX state transitions honored
- Ranker honesty fix: skip completed E3/post-merge candidates via `_story_is_done` (required so re-rank does not rebind completed work)

### OUT

- Any lower-ROI unlocked item (must wait for next cycle)
- Blocked external work unless this card is exactly that and resources exist
- Scope expansion / architecture tourism without DoD link
- Portal publico, multi-tenant, billing, K8s/Kafka/Redis/ES without demonstrated need
- Physical works tracking / auto-protocol without human action

---

## Acceptance Criteria

1. **Given** the workspace CLI module exists (`python3 -m scripts.workspace`), **When** @dev runs `today`, `opportunities`, `dossier` (valid id or documented offline/no-id path), and `coverage`, **Then** each command’s exit code and stdout/stderr summary are recorded in the evidence pack (no silent failures).
2. **Given** the run completes (success or graceful degradation with non-zero exits documented), **When** evidence is collected, **Then** a reproducible pack is written under `docs/ops/session-*` and/or `output/*` (or a new dated session folder under those roots) including command inventory, timestamps, exit codes, and key output snippets/files.
3. **Given** DoD adversarial constraints, **When** this story is delivered, **Then** no READY seal is elevated (`LOCAL_RESILIENCE_READY`, `PRE_VPS_FINAL_READY` remain NOT_READY) and no VPS provision/ops work is performed.

---

## Tasks / Subtasks (for @dev)

- [x] Branch from mainline (non-main feature branch)
- [x] Run and capture: `python3 -m scripts.workspace today` (and/or `--json`)
- [x] Run and capture: `python3 -m scripts.workspace opportunities --status open` (limit as needed)
- [x] Run and capture: `python3 -m scripts.workspace dossier <id>` (or document offline/empty path if no id)
- [x] Run and capture: `python3 -m scripts.workspace coverage`
- [x] Persist evidence pack under `docs/ops/session-*` or `output/*`
- [x] Record exit codes + notes (local DB optional; offline fallback OK if documented)
- [x] Do **not** touch DoD READY seals or VPS
- [x] Include ranker `_story_is_done` fix + smoke test so re-rank skips completed E3/post-merge

---

## Test commands

- `python3 -m scripts.workspace --help`
- `python3 -m scripts.workspace today --json`
- `python3 -m scripts.workspace opportunities --status open --json` (or equivalent flags present in CLI)
- `python3 -m scripts.workspace dossier <id>` (or documented skip/offline)
- `python3 -m scripts.workspace coverage --json` (or text mode)
- `pytest squads/extra-dod-roi/tests/test_squad_smoke.py -v`

---

## Files (planned)

- `docs/ops/session-*` (evidence / session artifacts)
- `output/*` (CLI/session outputs)
- `docs/stories/ROI-cand-workspace-daily-evidence-pack.md` (progress only)
- `.aiox/state/stories/ROI-cand-workspace-daily-evidence-pack.json` (lifecycle state)

## File List (implemented)

- `docs/ops/session-2026-07-17-workspace-evidence/` — MANIFEST, exit_codes.tsv, captures (.txt/.payload.json)
- `output/workspace-evidence-20260717/` — mirror pack
- `squads/extra-dod-roi/scripts/rank_next_cli.py` — `_story_is_done` skips completed E3/post-merge
- `squads/extra-dod-roi/tests/test_squad_smoke.py` — regression for completed-candidate skip
- `docs/ops/session-2026-07-17-workspace-evidence/handoff-dev-to-qa.yaml`
- `docs/stories/ROI-cand-workspace-daily-evidence-pack.md`
- `.aiox/state/stories/ROI-cand-workspace-daily-evidence-pack.json`

---

## Dev Notes — command results (honest)

| Command | Exit | Notes |
|---------|------|-------|
| workspace --help | 0 | subcommands today/opportunities/dossier/coverage present |
| today --help | 0 | |
| today --json | 0 | `pg_available=false`; timeout 127.0.0.1:5433; offline sections built |
| opportunities --help | 0 | |
| opportunities --status open --limit 5 --json | 0 | `status=DEGRADED`, count=5 session fallback |
| coverage --help | 0 | |
| coverage --json | 0 | commercial ~10.61%; **not** 95%; disclaimer present |
| dossier --help | 0 | |
| dossier offline-no-id-probe --json | **1** | `NOT_FOUND` — expected non-silent fail |
| dossier 8504275 --json | 0 | offline session OK; pg_error still reported |
| pytest test_squad_smoke | 0 | 10 passed |

Evidence: `docs/ops/session-2026-07-17-workspace-evidence/MANIFEST.md`

---

## Risks

- May need local DB — mitigate via offline/session fallbacks already in workspace CLI; document degradation
- `dossier` needs a real opportunity id when live data absent — document offline path

## Dependencies

- workspace CLI module (`scripts/workspace/`, commands: today/opportunities/dossier/coverage)
- Existing session artifacts under `docs/ops/session-2026-07-17` (optional input, not VPS)

## Rollback

Revert feature branch commits; never update DoD on failure; no merge.

## Claims if PASS

- Only claims backed by new evidence
- Workspace cotidiano commands executed with recorded exit codes (evidence pack)

## Claims still forbidden

- VPS provisionada/operacional sem evidência live
- Cobertura operacional 95% sem medição estrita
- Freshness live garantida por fixtures
- LOCAL_RESILIENCE_READY (superseded → NOT_READY)
- PRE_VPS_FINAL_READY sem live canary + PG evidence
- Stories Done sem QA/PO independentes
- Any READY seal promotion from this story alone

---

## AIOX DoD for this story

- [x] @po validated (Ready)
- [x] @dev implemented on non-main branch
- [x] Tests/lint per risk level (pytest squad smoke PASS; evidence commands recorded)
- [x] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer) — **PASS** 2026-07-17
- [x] @po closed — **2026-07-17** (no READY seals; publication authorized for @devops draft PR)
- [ ] @devops draft PR / publish path (no auto-merge)
- [x] DoD.md checkboxes only if evidence authorizes — **no DoD READY elevation authorized**

---

## QA Results

**Reviewer:** Quinn (@qa / adversarial-qa-auditor)  
**Date:** 2026-07-17T22:45:00Z  
**Independent:** yes (≠ implementer Dex/@dev)  
**Reviewed commit:** `7d39b895c625122a19a2b7395ad8ca872e2db396`  
**Gate file:** `squads/extra-dod-roi/state/qa/cyc-2026-07-17T223227Z-qa.json`  
**Verdict:** **PASS**

### AC traceability

| AC | Result | Evidence |
|----|--------|----------|
| 1 Commands + exit codes recorded | **PASS** | `exit_codes.tsv` + captures; today/opportunities/coverage exit 0 degraded; dossier bogus exit 1 NOT_FOUND; dossier 8504275 exit 0 offline |
| 2 Pack under docs/ops and/or output | **PASS** | `docs/ops/session-2026-07-17-workspace-evidence/` + `output/workspace-evidence-20260717/` |
| 3 No READY seals / no VPS | **PASS** | No `DOD.md` in branch diff; MANIFEST forbids LOCAL_RESILIENCE_READY, PRE_VPS_FINAL_READY, 95%, VPS |

### Reproduction (QA)

- `pytest squads/extra-dod-roi/tests/test_squad_smoke.py -q` → **10 passed** (~60s)
- `enforce_aiox_path.py qa` → ok (after restoring `current.json` to cycle `cyc-2026-07-17T223227Z` IN_REVIEW)
- Spot-check payloads: `pg_available=false`, opportunities `DEGRADED` count=5 id `8504275`, coverage commercial **10.61%** (not 95%), disclaimer present

### Residual (non-blocking)

1. **LOW/process:** aborted INIT cycles had overwritten `state/cycles/current.json` while this cycle was still IN_REVIEW — restored before enforce.
2. **LOW/docs:** coverage metric objects use `status=READY` as schema readiness (e.g. commercial 10.61%, operational_source_coverage 0%) — **not** DoD seals.

### Gate decision

**PASS** → next phase **PO_CLOSE** (@po only). QA did **not** set `po_closed`, did **not** push, did **not** promote READY seals. Story remains **InReview** until @po closes.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-17 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-17 | 1.0.0 | Validated GO (9/10) — Status: Draft → Ready; ACs/tasks sharpened for workspace evidence pack | @po |
| 2026-07-17 | @dev (Dex) | Status: Ready → InProgress → InReview. Evidence pack under docs/ops/session-2026-07-17-workspace-evidence + output mirror. Ranker `_story_is_done` fix + smoke test. Handoff to @qa. |
| 2026-07-17 | @qa (Quinn) | Independent QA **PASS**. Gate `squads/extra-dod-roi/state/qa/cyc-2026-07-17T223227Z-qa.json`. Cycle advanced IN_REVIEW → QA; next=PO_CLOSE. Story left open (not closed by QA). No READY seals. |
| 2026-07-17 | 1.0.1 | PO close after QA PASS — Status: InReview → Done; po_closed=true; publication_authorized=true. [closure-key: ROI-cand-workspace-daily-evidence-pack:commit:7d39b895c625122a19a2b7395ad8ca872e2db396] No READY seals / no VPS / no DoD.md promotion. | @po |

---

## PO Close

**Closed by:** Pax (@po)  
**Closed at:** 2026-07-17T22:47:00Z  
**Closure key:** `ROI-cand-workspace-daily-evidence-pack:commit:7d39b895c625122a19a2b7395ad8ca872e2db396`  
**QA verdict:** PASS (Quinn, independent)  
**Reviewed commit:** `7d39b895c625122a19a2b7395ad8ca872e2db396`  
**Gates:** lint=PASS, tests=PASS, typecheck=NA, build=NA  
**publication_authorized:** true (draft PR path for @devops only; no auto-merge; no push by @po)  
**DoD seals:** LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY remain NOT_READY — not elevated  
**Follow-ups (non-blocking):** cycle `current.json` clobber by aborted INIT tests; metric `status=READY` is schema readiness not DoD seal  

**Next:** @devops draft PR / publish path for cycle PUBLISH (no force-push, no auto-merge).

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
