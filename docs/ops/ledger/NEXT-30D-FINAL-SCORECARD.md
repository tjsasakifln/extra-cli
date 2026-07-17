# NEXT-30D Final Scorecard

**Campaign:** NEXT-30D-MULTIAGENT  
**Base SHA:** `77ff8a8`  
**Date:** 2026-07-17  

## Task status (executable vs blocked)

| ID | Status | Evidence | Blocker |
|----|--------|----------|---------|
| L1.8 | **DONE** | GATE-1 + NEXT-30D-BASELINE | — |
| C2.3 | **DONE** | PNCP path + 049 prior; residual API timeouts as ops risk | — |
| C2.4–C2.6 | **DONE** | Prior campaign evidence (not re-counted as new) | — |
| K3.1 | **DONE** | schema audit + k3 baseline | — |
| Q5.1 | **DONE** | critical tests | — |
| Q5.4 | **DONE** | remediation 44→4 residual documented | residual 4 ruff rules (policy) |
| C2.7 | **DONE** + **BLOCKED_EXTERNAL residual** | sc_compras 2602 DONE; DOE-SC blocked | DOE_SC_* creds (Tiago) |
| C2.8 | **DONE** | dedup CLI + rows | — |
| C2.9 | **DONE** | active_snapshot_integrity=1.0 | — |
| K3.2 | **DONE** | on-disk `pilot-90d-next30d.json` **status=success** (days=1 full window); checkpoint `completed_windows=["20260715_20260715"]`; DB 31k+ | Full 90d multi-window resume optional overnight; do not leave status=running on disk |
| K3.3 | **BLOCKED_EXTERNAL** / deferred | needs alt contract sources prioritization | product priority |
| K3.4 | **DONE** (prep) | incremental path exists post-pilot; not full aditivos pipeline | follow-up |
| C2.10 | **DONE** | coverage audit 4.76% measured | — |
| C2.11 | **DONE** (escalate) | `c2.11-editais-gap-escalate-next30d.md` | 95% remains open DoD item |
| V6.2 | **BLOCKED_EXTERNAL** | procurement pack | Tiago pay/VPS |

## Critical path PERT (≥30)

| Order | ID | PERT | Status | Cum |
|-------|-----|------|--------|-----|
| 1 | C2.7 | 15 | DONE (public) + DOE BLOCKED residual | 15 |
| 2 | C2.10 | 5 | DONE (measured) | 20 |
| 3 | C2.11 | 10 | DONE (formal escalate, not fake 95%) | **30** |

## Metrics before → after

| Metric | Before | After |
|--------|--------|-------|
| pncp_raw_bids | 346 | ~2948+ |
| pncp_supplier_contracts | 0 | **31219** |
| dedup_cross_source | 0 | **5** |
| editais crude % (52/1093) | ~3.1% | **4.76%** |
| golden fail-closed tests | 0 | **9** |
| schema audit missing_required | — | **[]** exit 0 |
| pilot status | none | **success** |

## Gates

| Gate | Verdict |
|------|---------|
| A FOUNDATION_TRUTH | **PASS** (migration inventory CONCERNS documented, not silent) |
| B DATA_EXPANSION | **PASS** with BLOCKED_EXTERNAL DOE-SC |
| C INTELLIGENCE_OUTPUT | **PASS** (PDF×Excel CONSISTENT same run_id) |
| D CAMPAIGN_ACCEPTANCE | **PASS** (CP 30 closed via C2.7+C2.10+C2.11; no 95%/LOCAL_READY claim) |

## Forbidden claims (still)

- ≥95% editais/contratos  
- LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE  
- Full 90d multi-window walk (only 1d terminal window proven this close-out; cumulative DB larger from prior partials)
