# BASELINE — NEXT-30D-ROI-MAIN

**Recorded (UTC):** 2026-07-18T19:19:39Z  
**HEAD:** `fbc586856332db11ecb21ae4524dfdf29dd90857`  
**origin/main:** `fbc586856332db11ecb21ae4524dfdf29dd90857`  
**Branch:** `main`  
**Workspace:** clean=True · synced=True

## DoD (parsed live — checkboxes NOT modified)

| Metric | Value |
|--------|-------|
| SHA-256 | `54bbbc0a0eec4576989722d9a1167860e1322c5cd509804d3677638e8c657228` |
| Total items | 1355 |
| Checked `[x]` | 92 |
| Open `[ ]` | 1263 |

## Gates (fail-closed)

| Gate | Status | Class |
|------|--------|-------|
| LOCAL_READY | NOT_READY | nao_comprovado |
| PRE_VPS_FINAL_READY | NOT_READY | nao_comprovado |
| VPS_OPERATIONAL | NOT_READY | nao_comprovado |
| PROJECT_DONE | NOT_READY | nao_comprovado |
| LOCAL_RESILIENCE_READY | NOT_READY | parcialmente_comprovado |

## Operational coverage (honest)

- Editais crude metric: **~4.76%** (52/1093 style metrics in next30d-metrics-final; multi-source artifacts 2026-07-17) → **stale / parcialmente_comprovado**
- Recall benchmark: PARTIAL (4/4 sample; missing strata) → **nao_comprovado** for ≥95% claim
- Pilot 90d national: **not_completed** / path_proof only → **parcialmente_comprovado**
- 3y backfill: **NO-GO**

## Quality probes at baseline

| Probe | Result | Class |
|-------|--------|-------|
| PostgreSQL local :5433 | reachable (psycopg2) | executado |
| extra-dod-roi tests | 58 passed / 1 failed | parcialmente_comprovado |
| ruff (squad scripts) | 64 errors reported | nao_comprovado |
| Full pytest / mypy / bandit / pip-audit | not run at baseline | nao_comprovado |
| `.env.example` | present (~200 lines) | implementado |

## Prior work NOT reusable as new advance

1. **dod-50-current SUCCESS** — 50 flips already counted (main via PR #25 family).
2. **Earlier NEXT-30D / PE-30D windows** already executed on the graph.
3. **epic/advance-30d-local-ready-20260718** — not on main; must not be double-counted.

## extra-dod-roi conflict

Current mode: **branch + draft PR** (MAIN_WRITE abort, open-draft-pr step).  
Campaign requires: **main-direct**.  
Rankings/requirements: **STALE** vs current main DOD hash.

## First delivery after baseline

1. Implement and test `main-direct` mode.
2. Re-rank from fresh main truth.
3. Freeze PLAN-30D / PERT / scope.json.
4. Execute ROI cycles on main with writer lock + independent QA + push to origin/main.

## Classification legend

implementado · testado · executado · comprovado_live · parcialmente_comprovado · nao_comprovado · stale · bloqueado · nao_aplicavel · concluido
