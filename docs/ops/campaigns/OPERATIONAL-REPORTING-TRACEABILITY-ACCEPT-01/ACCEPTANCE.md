# ACCEPTANCE — OPERATIONAL-REPORTING-TRACEABILITY-ACCEPT-01

## Terminal (honest)

**FAILED_PREMORTEM** — `MAXIMUM_PR_COUNT=3` exceeded (actual merged PRs: **4**: #159, #160, #161, #163).

Controller accepts and deltas are **factual** but do **not** authorize `BUNDLE_ACCEPTED`.

## Factual outcomes (not campaign success)

| Metric | Value |
|--------|-------|
| RAW_DOD_DELTA | 40 |
| WEIGHTED_DOD_DELTA | 176 |
| N_ACCEPTED | 441 |
| N_OPEN | 1020 |
| Live proofs OK this tip | 40/40 |

## PRs

1. #159 fail-closed lists + metadata  
2. #160 vertical reports + real PDF/Excel  
3. #161 DOD promotion  
4. #163 evidence integrity (technical; broke PR budget)

## Integrity notes

- `verify_result.json` recaptured from live `orpt_item_proofs` (duration_s > 0, real stdout).  
- ORPT-30-02: crawl fail/timeout → reliability PARTIAL, not READY.  
- Empty DB: SUCCESS_ZERO/NOT_READY documented; no CMI fixture as market proof.
