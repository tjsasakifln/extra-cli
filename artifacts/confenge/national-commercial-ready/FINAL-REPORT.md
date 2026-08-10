# FINAL-REPORT — National commercial reservoir

## Coverage

`FULLY_RECONCILED=true` · ratio=1.0 · unexplained_missing=0

## Classification (live SHADOW)

| Class | N |
|------|--:|
| TARGET_CONFIRMED | 8382 |
| TARGET_PROBABLE_RESEARCH | 26083 |
| TARGET_OUT_OF_SCOPE | 92543 |
| TARGET_INSUFFICIENT_EVIDENCE | 386642 |

## Contact enrichment

- Process-first national harvest: **running** (10 parallel root shards, no Top-N)
- Continuous site/web enrich-continuous: **running** (resume, no max_companies)
- Intermediate harvest accounts: ~298+
- Process EMAIL_SEND_READY proxy: 8
- Historical harvest ESR: 60
- MIN_OPERATIONAL_RESERVE: **900** (10/h × 9h × 10d)

## Terminal state (honest)

Workers draining. Until 100% CONFIRMED have contact terminal states and ESR≥900,
`NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY` remains false if ESR gap persists after full ladder.

SHA binding: origin/main = host = b8f9d1c6… (PR #217). Process harvest on PR #222.
