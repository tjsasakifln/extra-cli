# BASELINE — advance-30d-operational-20260718

Generated after forensic recovery. Numbers from HEAD, not assumed.

## Recovery result

- **Local work found:** YES — 12 unpushed commits on `epic/advance-30d-local-ready-20260718`
- **Published:** epic tip + rescue branch + recovery commit `cb0be3b`
- **Decision:** continue existing epic (do not reset to main and discard 48+ slices)

## Verified SHAs

| Ref | SHA |
|-----|-----|
| main / origin/main | `fbc586856332db11ecb21ae4524dfdf29dd90857` |
| epic (published recovery base) | see baseline.json |
| feature in flight | `58d9a83a5cac663cc8f70c169b5dead85f6eada5` (requirement states) |

## DoD

- Remote-known historical: **92** accepted (pre-campaign claim)
- Current HEAD: see `baseline.json` `dod.checked/total`
- Gates LOCAL_READY / PRE_VPS / VPS / PROJECT_DONE: **not ready / blocked**

## Metrics (contract-report 2026-07-17 — STALE until re-run)

| Metric | Status |
|--------|--------|
| Operational coverage | 0/1093 (0%) READY but stale |
| Commercial signal | 116/1093 (10.61%) — not coverage |
| Source mapping | 1093/1093 |
| Freshness | NOT_READY |
| Recall | NOT_READY |
| Completeness | ~17.65% |

## Current AIOX cycle

- Story: `ROI-cand-dyn-slice-b8d41f43fbfc`
- Phase: IN_REVIEW → re-QA after FAIL remediação
- Next: independent QA → PO close only on PASS/CONCERNS → merge epic → force-next
