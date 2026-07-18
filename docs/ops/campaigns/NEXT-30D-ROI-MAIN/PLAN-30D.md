# PLAN-30D — NEXT-30D-ROI-MAIN

**Frozen (UTC):** 2026-07-18T19:26:01Z  
**HEAD:** `7768f057e37a287e738a37ea18bb302848228b19`  
**Baseline HEAD:** `fbc5868…`  
**Critical path:** **30.5 business days** (target ≥30) · meets=True

## Intent
Advance critical path toward `LOCAL_READY` from main (92/1355 DoD). Exclude prior windows from advance accounting.

## Critical path
| ID | Task | d | ES | EF |
|----|------|---|----|----|
| T00 | Baseline + main-direct mode | 1.0 | 0.0 | 1.0 |
| T01 | Fresh rank + campaign freeze (PLAN/PERT/scope) | 0.5 | 1.0 | 1.5 |
| T03 | Clean bootstrap + migrations + schema audit proof on PG | 2.0 | 1.5 | 3.5 |
| T04 | Global/critical pytest green with real PostgreSQL | 2.5 | 3.5 | 6.0 |
| T06 | Universe canonical import: hash, zero-dup, change detection | 2.0 | 3.5 | 5.5 |
| T07 | Source registry + applicability matrix complete for editais/contratos | 2.5 | 5.5 | 8.0 |
| T05 | Golden path local end-to-end executable + evidence | 2.0 | 6.0 | 8.0 |
| T08 | Editais crawl: checkpoint/resume/raw-zone/provenance priority sources | 3.0 | 8.0 | 11.0 |
| T09 | Coverage operational machinery: stages, denominators, entity progress | 3.0 | 11.0 | 14.0 |
| T10 | Coverage scale M2: multi-entity collection with provenance | 3.0 | 14.0 | 17.0 |
| T10b | Coverage scale M3: expand operational coverage toward gate trajectory | 3.0 | 17.0 | 20.0 |
| T15 | Operational outputs: opportunities, triage, dossier, weekly/monthly | 2.5 | 20.0 | 22.5 |
| T16 | PDF+Excel generation + reconciliation proof | 1.5 | 22.5 | 24.0 |
| T18 | DoD reconciliation: flip only evidence-backed items from this window | 1.0 | 24.0 | 25.0 |
| T19 | Campaign close: final report, skeptic audit, next backlog | 1.0 | 25.0 | 26.0 |

## All tasks
| ID | Crit | Status | d | Preds | Name |
|----|------|--------|---|-------|------|
| T00 | Y | DONE | 1.0 | — | Baseline + main-direct mode |
| T01 | Y | DONE | 0.5 | T00 | Fresh rank + campaign freeze (PLAN/PERT/scope) |
| T02 |  | PLANNED | 1.0 | T01 | Fail-closed mandatory gates: no || true in CI/Makefile gates |
| T03 | Y | PLANNED | 2.0 | T01 | Clean bootstrap + migrations + schema audit proof on PG |
| T04 | Y | PLANNED | 2.5 | T03 | Global/critical pytest green with real PostgreSQL |
| T05 | Y | PLANNED | 2.0 | T04 | Golden path local end-to-end executable + evidence |
| T06 | Y | PLANNED | 2.0 | T03 | Universe canonical import: hash, zero-dup, change detection |
| T07 | Y | PLANNED | 2.5 | T06 | Source registry + applicability matrix complete for editais/contratos |
| T08 | Y | PLANNED | 3.0 | T07,T05 | Editais crawl: checkpoint/resume/raw-zone/provenance priority sources |
| T09 | Y | PLANNED | 3.0 | T08 | Coverage operational machinery: stages, denominators, entity progress |
| T10 | Y | PLANNED | 3.0 | T09 | Coverage scale M2: multi-entity collection with provenance |
| T10b | Y | PLANNED | 3.0 | T10 | Coverage scale M3: expand operational coverage toward gate trajectory |
| T11 |  | PLANNED | 3.0 | T07 | Contracts historical backfill windows + incremental upsert |
| T12 |  | PLANNED | 2.0 | T09 | Snapshot integrity 100% + conflict/reconcile reports |
| T13 |  | PLANNED | 2.0 | T08 | Recall stratified sample expansion + independent gold set |
| T14 |  | PLANNED | 2.0 | T11,T10 | Competitors/winners/values: denominators + NOT_READY when insufficient |
| T15 | Y | PLANNED | 2.5 | T10b,T12 | Operational outputs: opportunities, triage, dossier, weekly/monthly |
| T16 | Y | PLANNED | 1.5 | T15 | PDF+Excel generation + reconciliation proof |
| T17 |  | PLANNED | 1.5 | T05,T06 | Backup/restore local re-proof with provenance+universe |
| T18 | Y | PLANNED | 1.0 | T16,T17 | DoD reconciliation: flip only evidence-backed items from this window |
| T19 | Y | PLANNED | 1.0 | T18 | Campaign close: final report, skeptic audit, next backlog |
| T20 |  | PLANNED | 1.0 | T01 | Claim-language / indicator catalog honesty residual |
| T21 |  | PLANNED | 1.5 | T08 | Crawler metrics + structured logs operational proof |
| T22 |  | PLANNED | 1.5 | T09 | Alert pipeline residual + freshness monitors |
| T23 |  | PLANNED | 1.5 | T05,T09 | Freshness/data-presence reports automated on golden path |
| T24 |  | PLANNED | 1.0 | T08,T00 | Resume-after-interrupt protocol tested for crawlers and campaign |

## Rules
1. main-direct (writer lock, independent QA, push origin/main, no PR/force-push)
2. Re-rank after each accepted increment
3. Prefer coverage/universe/golden-path vertical slices
4. BLOCKED external/human gets dossier — not fake DONE
