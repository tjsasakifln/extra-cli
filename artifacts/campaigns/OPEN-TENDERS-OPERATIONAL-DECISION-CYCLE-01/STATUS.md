# OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01 — Status

**SHA candidate:** `c51c2e85f2e432a71326f4c34575634056f2e5d3`  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/127  

## Measured results (VPS)

| Gate | Result |
|------|--------|
| PNCP open monitoring complete (19/19 modalities) | **PASS** (`scope_complete=true`, 4 records) |
| Snapshot integrity 100% (active open) | **PASS** (4/4 after membership-key fix) |
| Deliverable E live operational audit | **PASS** (4 recommendations) |
| Applicability unknown | **0** (was 147) |
| Dual open_tenders coverage | **38.9%** (425/1093) — FAIL ≥95% |
| Fresh count (dual report) | 1093 |
| extra-weekly.timer | **enabled + active** (next Mon 2026-07-27 03:30) |
| Soak 7d | **IN_PROGRESS** (day 0) |
| CI on PR | see checks on #127 |

## Material bugs fixed in campaign

1. Weekly path orphaned per-modalidade collect → aggregated `run_pncp_open_monitoring`
2. coverage_evidence ON CONFLICT vs migration 059 canonical unique
3. Membership keys ignored raw `numeroControlePNCP` → false mass inactivation

## Remaining to campaign PASS

1. CIGA dual `coverage_evidence` for municipal (current CIGA crawler matches 0 DB entities / does not fill dual evidence)
2. Coverage ≥95% of 1093
3. Soak 7 days without silent gaps
4. Merge main + DOD ACCEPTED only with CI green + evidence

## Honest verdict

**Foundation + first live operational cycle: PASS**  
**Full campaign operational PASS (coverage≥95% + soak): BLOCKED** on CIGA dual evidence + calendar soak.
