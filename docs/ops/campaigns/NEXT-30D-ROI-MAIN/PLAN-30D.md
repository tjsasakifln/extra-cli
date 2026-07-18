# PLAN-30D (delta pós-herança) — NEXT-30D-ROI-MAIN

**Frozen:** 2026-07-18T20:12:35Z · **HEAD:** `83b1b042ff2a1ec110f36e35af5c955ff31ce744`  
**Critical path (NEW only):** **19.5 business days** (target ≥30)

## Metric lineage

| Layer | Acceptance |
|-------|------------|
| Epic historical (not main) | 32.3% (437/1354 @ 0bd5074) |
| Main pre-recon baseline | ~6.8% (92/1355) |
| Main after inherited port | **14.4% (195/1355)** |
| New PERT this window | tasks N01–N15 only |

## Critical path

| ID | Task | d | ES | EF |
|----|------|---|----|----|
| H0 | Inherited recon freeze (code+S5+DoD flips) | 0 | 0.0 | 0.0 |
| N02 | Universe reimport hash+zero-dup proof on main PG | 2.0 | 0.0 | 2.0 |
| N04 | Source registry applicability zero necessary unknown | 2.5 | 2.0 | 4.5 |
| N05 | Coverage operational stages provenance M2 scale slice | 4.0 | 4.5 | 8.5 |
| N06 | Coverage scale M3 expand entities with evidence | 4.0 | 8.5 | 12.5 |
| N11 | Operational daily/weekly package live run on main data | 2.5 | 12.5 | 15.0 |
| N12 | PDF+Excel reconcile live package | 1.5 | 15.0 | 16.5 |
| N14 | DoD residual REVALIDATE batch with evidence | 2.0 | 16.5 | 18.5 |
| N15 | Campaign close report + skeptic audit + next backlog | 1.0 | 18.5 | 19.5 |

## Rules
- Do not re-count inherited flips as new advance
- main-direct, independent QA, no PR
- Fail-closed gates; no LOCAL_READY without criteria
