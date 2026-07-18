# LEGACY WORK RECONCILIATION — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T20:34:59Z  
**Main:** `dc7cea0efb3f` · **Epic:** `0bd5074a0c4e` · **Merge-base:** `fbc586856332`  
**PR #28:** OPEN (historical only — not delivery)

## Relationship to R1

Full forensic pass already in `docs/ops/campaigns/NEXT-30D-ROI-MAIN/LEGACY-BRANCH-RECONCILIATION.md`.  
R2 **does not re-count** R1 inherited flips (102) or R1 PERT days (4.5).

## Metric lineage

| Layer | % |
|-------|--:|
| Epic @ 0bd5074 | 32.3 |
| Main pre-recon | 6.8 |
| Main after R1 inherited | 14.4 |
| Main R2 start | 14.39 |

## File classification (epic delta vs merge-base vs main HEAD)

| Class | Count |
|-------|------:|
| ALREADY_IN_MAIN | 207 |
| DOCUMENTATION_ONLY | 10 |
| PORT_VALIDATED | 1 |
| REVALIDATE | 399 |

Product paths still PORT/REVALIDATE (sample): see `legacy-work-reconciliation.json`.

## Decisions

| Item | Class | Decision |
|------|-------|----------|
| Blind cherry-pick | INVALID_FALSE_GREEN | REJECT |
| Restore 32.3% | INVALID_FALSE_GREEN | REJECT |
| R1 wave1 on main | ALREADY_IN_MAIN | KEEP |
| mig 056 WIP | REVALIDATE | COMMIT after tests |
| Epic session packs | DOCUMENTATION_ONLY | REFERENCE |

## Dirty WIP to integrate this cycle

1. `056_drop_supplier_entity_fk_contracts.sql`
2. `apply_migrations.py` max=56 (min=1)
3. `golden_path.py` PNCP timeout 360s
