# Acceptance criteria — A data inicial do backfill é registrada.

**Item:** `DOD-rol-1-definition-of-done-00e53389b2`  
**DOD line:** 753  
**Campaign:** HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

## Requirement
A data inicial do backfill é registrada.

## Given/When/Then
Given checkpoint `data/contracts_checkpoints/hc_closure_3y/contracts_full.json`  
When completed_windows are parsed  
Then the required bound date is recorded and asserted.

## Non-claims
Not LOCAL_READY / VPS_OPERATIONAL / offsite / soak 7d.
