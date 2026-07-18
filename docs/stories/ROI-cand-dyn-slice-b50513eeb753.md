# Story: [12.2 Saídas operacionais] Lista de editais acionáveis. · Lista de editais para revisão. · Lista de editais descartados com motivo. (+5 more)

**Story ID:** `ROI-cand-dyn-slice-b50513eeb753`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Done  

**Risk level:** **HIGH-RISK**  
**Source:** squad `extra-dod-roi` force-next (cycle `cyc-2026-07-18T153340Z`)  
**Candidate ID:** `cand-dyn-slice:b50513eeb753`  
**ROI:** `1.9615`  
**DoD refs:** 12.2 Saídas operacionais — first 8 list items

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **CLI-generated operational lists for triage (GO/REVIEW/NO_GO), snapshot removals, coverage gaps, source blockers and stale runs**,  
so that **§12.2 first eight DoD items are proven with executable evidence, not documentation theater**.

---

## Problem / Value

### Problem

§12.2 open items for operational list outputs lack a single fail-closed generator with run metadata, CSV artifacts and honest empty/limitation handling.

### Value

Operational triage lists unblock daily consulting workflow and produce evidence for DoD §12.2 without claiming 95% coverage or LOCAL_READY.

---

## Scope

### IN

- Module `scripts/reports/operational_outputs.py`
- Deterministic classification GO/REVIEW/NO_GO via existing `compute_ranking` when `opportunity_intel` empty
- Eight list artifacts + manifest JSON with run_id, as_of, reliability
- Unit tests + live PG evidence session
- DoD checkbox flips only after independent QA PASS and real files

### OUT

- Full universe coverage 95%
- Contract backfill 3y
- PDF/Excel commercial pack (later slices)
- LOCAL_READY / PRE_VPS seals
- Inventing competitors or rankings without data

### The 8 DoD items

1. Lista de editais acionáveis (GO)
2. Lista de editais para revisão (REVIEW)
3. Lista de editais descartados com motivo (NO_GO + reason)
4. Lista de oportunidades removidas do snapshot (`is_active=false`)
5. Lista de entes sem cobertura de editais
6. Lista de entes sem cobertura de contratos
7. Lista de blockers por fonte
8. Lista de runs stale

---

## Acceptance Criteria

1. **Given** PostgreSQL with any `pncp_raw_bids`, **When** `python3 -m scripts.reports.operational_outputs --dsn $DSN --out DIR` runs, **Then** exit 0 and produces 8 CSV (+ optional empty) files and `manifest.json` with `run_id`, `generated_at`, `reliability`.
2. **Given** active bids, **When** lists are generated, **Then** each active bid appears in exactly one of GO/REVIEW/NO_GO; discarded rows include `motivo`.
3. **Given** empty entity tables, **When** gap lists are generated, **Then** files exist with header or empty body and manifest documents limitation — never invents entities.
4. **Given** ingestion_runs older than SLA or stuck `running`, **When** stale list runs, **Then** those runs appear in `runs_stale.csv`.
5. **Given** independent QA, **When** tests pass and live artifacts verified, **Then** only proven §12.2 items may be `[x]` in DOD.md.
6. **No** NOT_APPLICABLE used to hit campaign meta; **no** LOCAL_READY / 95% claims.

---

## Test commands

```bash
python3 -m pytest tests/test_operational_outputs.py -q --no-cov
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m scripts.reports.operational_outputs --dsn "$LOCAL_DATALAKE_DSN" --out docs/ops/session-*/lists --json
```

---

## Files (planned)

- `scripts/reports/operational_outputs.py`
- `tests/test_operational_outputs.py`
- `docs/ops/session-2026-07-18-operational-outputs/`
- `DOD.md` (only after QA)
- story + state

---

## Risks

- Over-marking without real evidence
- Empty universe mistaken for full coverage of gap lists
- Ranking on incomplete bid fields → many NO_GO (honest, not a bug)

## Rollback

Revert feature branch commits; never update DoD on failure; no merge to main.

## Claims if PASS

- Operational list generator exists and produces 8 list types with evidence
- Active bids classified into GO/REVIEW/NO_GO with reasons

## Claims still forbidden

- Cobertura operacional 95%
- LOCAL_READY / PRE_VPS_FINAL_READY / VPS_OPERATIONAL / PROJECT_DONE
- Recall ≥95%
- Backfill 3 anos completo

---

## AIOX DoD for this story

- [x] @po validated (Ready)
- [x] @dev implemented on non-main branch
- [x] Tests/lint per risk level
- [x] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer)
- [x] @po closed
- [x] @devops publish on epic branch (no main merge)
- [x] DoD.md 8 list items flipped with evidence

---

## QA Results

**Reviewer:** Quinn (@qa)  
**Date:** 2026-07-18T15:40:18Z  
**Reviewed revision:** `c043458`  
**Verdict:** **PASS**

Independent adversarial audit of DoD §12.2 first 8 list items. Full write-up: `docs/ops/session-2026-07-18-operational-outputs/QA-VERDICT.md`.

| # | Item | Class |
|---|------|-------|
| 1 | editais acionáveis | DONE |
| 2 | editais revisão | DONE |
| 3 | editais descartados + motivo | DONE |
| 4 | oportunidades removidas snapshot | DONE |
| 5 | entes sem cobertura editais | DONE |
| 6 | entes sem cobertura contratos | DONE |
| 7 | blockers por fonte | DONE |
| 8 | runs stale | DONE |

**Evidence:** pytest 5 passed (exit 0); live `operational_outputs` exit 0 → GO=6/REVIEW=1/NO_GO=1 partition equals 8 active bids; motivo present; empty gap lists + limitation; forbidden includes LOCAL_READY; stale capability via stuck_running_hours=0 → 2 rows.

**May flip DoD.md:** all 8 list lines only. **Must not claim:** LOCAL_READY, 95% coverage, universe-complete gaps.

**Residual risks:** hardcoded `fonte_confiavel=True`; LIMIT 2000 undocumented; gap/removed non-empty paths not live-exercised.

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-18 | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |
| 2026-07-18 | @po | Ready — ACs measurable, scope = 8 lists, no seal claims |
| 2026-07-18 | @qa (Quinn) | Independent PASS — 8/8 list capability DONE; QA-VERDICT.md |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
| 2026-07-18 | @dev | Implemented operational_outputs + tests + live lists |
| 2026-07-18 | @qa | PASS all 8 items (independent) |
| 2026-07-18 | @po | Closed after QA PASS; DoD §12.2 first 8 [x] |
