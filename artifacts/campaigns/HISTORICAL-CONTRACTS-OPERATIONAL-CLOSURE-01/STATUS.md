# Campaign STATUS — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Updated:** 2026-07-23T14:11Z  
**Branch:** `campaign/historical-contracts-operational-closure-01`  
**HEAD foundation work:** in progress (not yet committed as single foundation SHA)

## Result so far (honest — NOT final PASS)

| Gate | Status |
|------|--------|
| Baseline inventory | DONE (baseline.json revalidated 2026-07-23) |
| Spec 002 converged | DONE (VPS/cutover/soak in scope; converge-report.md) |
| Applicability policy | DONE (reproof dual after projection still required) |
| Entity evidence + proof gate | DONE (flags alone cannot write success_zero) |
| Live 7d/90d pilots | DONE GO for 3y |
| Live 3y backfill | **IN PROGRESS** ~28/37; PID local writer; 9 missing windows |
| Export/restore fail-closed | DONE (code); cutover drill OPEN |
| systemd repo + validate | DONE; host health OK exit 0; failed units cleared for health |
| Dual ≥95% | NOT YET (needs full windows + projection) |
| Off-site backup / soak / DOD | NOT YET |
| Claim operational PASS | **FORBIDDEN** |

## Writer

- Canonical writer: **laptop** PID run_contracts_90d_pilot (single writer)
- VPS PNCP crawl timers: **disabled**

## Missing windows (sample)

See checkpoint; 9 remaining including retry of partial 20250311_20250409 (HTTP 422).

## Non-claims

No LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE / open_tenders 95% / fabricated success_zero.
