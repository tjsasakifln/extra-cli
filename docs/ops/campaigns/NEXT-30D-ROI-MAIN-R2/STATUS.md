# STATUS — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T21:17:16Z  
**HEAD baseline:** `dc7cea0` · **latest:** see git  
**DoD acceptance (canonical main):** 195/1355 = **14.39%** (not re-counted inherited as new)

## Metric lineage (separated)

| Layer | Value |
|-------|------:|
| Epic historical (not main) | 32.3% |
| Main R1 baseline | 6.8% |
| Main after R1 inherited | 14.4% |
| Main R2 (unchanged checkboxes) | 14.39% |
| **New critical PERT days this campaign** | **~20.0d / 32d** |
| Inherited PERT not re-counted | 4.5d |

## Scope terminals

DONE: R0 R1 R2 N02 N03 N04 N05 N06 N06b N07 N07b N10 N11 N12 N13  
IN_PROGRESS/CONCERNS: N01 (PNCP timeout in golden), N09 (recall scaffold)  
OPEN: N06c N08 N14 N15 N16 N17 N18  

## Gates

All seals NOT_READY (LOCAL_READY / VPS / PROJECT_DONE). Fail-closed.

## Resume

```bash
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/resume.md
python3 squads/extra-dod-roi/scripts/cli.py status
```
