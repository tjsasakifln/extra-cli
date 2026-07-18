# PLAN-30D — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T20:34:29Z · **HEAD:** `dc7cea0efb3f19b36a5133aabb235d89baf09cca`  
**Critical path (NEW):** **32.0 business days** (target ≥30)

## Metric lineage

| Layer | Acceptance |
|-------|------------|
| Epic historical (not main) | 32.3% (437/1354 @ 0bd5074) |
| Main R1 baseline | ~6.8% (92/1355) |
| Main after R1 inherited port | 14.4% (195/1355) |
| **Main R2 start** | **14.39% (195/1355)** |
| New PERT this window | tasks R0–N18 critical chain only |

## Critical path

`R0 → R1 → N02 → N04 → N05 → N06 → N06b → N06c → N11 → N12 → N14 → N15` = **32.0d**

| ID | Task | d |
|----|------|--:|
| R0 | R2 bootstrap recovery + lineage freeze | 0.5 |
| R1 | Legacy reconcile delta + commit mig056 WIP | 1.0 |
| N02 | Universe reimport hash+zero-dup on main PG | 2.0 |
| N04 | Source registry applicability zero necessary unknown | 2.5 |
| N05 | Coverage ops stages provenance M2 slice | 3.5 |
| N06 | Coverage scale M3 expand entities | 3.5 |
| N06b | Coverage scale M4 multi-source operational | 3.0 |
| N06c | Coverage scale M5 entity collection wave | 8.5 |
| N11 | Operational daily/weekly package live | 2.5 |
| N12 | PDF+Excel reconcile live package | 1.5 |
| N14 | DoD residual REVALIDATE batch evidence | 2.5 |
| N15 | Campaign close skeptic audit next backlog | 1.0 |

## Parallel (non-critical high ROI)

- R2 SmartLic reuse + snapshot bridge
- N01 golden path live
- N03 schema/migrations 056
- N07/N18 contracts machinery
- N09 recall + corpus
- N10 backup/restore
- N13 freshness
- N16/N17 residual

## Rules

- main-direct, independent QA, no PR
- Do not re-count R1 inherited flips
- Fail-closed gates; no LOCAL_READY without criteria
- SmartLic read-only; no SaaS architecture import
- Fixture ≠ live proof
