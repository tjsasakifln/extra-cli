# Acceptance criteria — dual historical_contracts >= 95%

**Item:** `DOD-rol-1-definition-of-done-c8d4fd6597`

## Requirement
`capability_monitoring_coverage(historical_contracts) >= 95%`.

## Given/When/Then
Given dual-coverage.json from campaign measurement
When gate_status and coverage_pct are read
Then PASS with coverage>=95%, denominator 1093, zero applicability unknown and identity unresolved.

## Non-claims
Not open_tenders, not LOCAL_READY, not VPS_OPERATIONAL, not soak 7d.
