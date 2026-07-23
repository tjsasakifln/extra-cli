# OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01 — Status

**PR:** https://github.com/tjsasakifln/extra-cli/pull/127  
**Verdict:** **BLOCKED** (only calendar soak remains)

## Dual coverage (VPS, regenerated)

| Metric | Value |
|--------|------:|
| universe | 1093 |
| applicable denominator | 1093 |
| covered | **1093** |
| coverage_pct | **100.0%** |
| gate | **PASS** |
| applicability unknown | **0** |
| pending | **0** |
| fresh_count | **1093** |

CIGA dual evidence: `project_ciga_dual_evidence` projected 668 municipal rows (`success_zero` 667 + `success_with_data` 1).

## verify-open-tenders-production

8/9 PASS — sole FAIL: `soak_7d` (timer armed, day 0).

## Remaining for campaign PASS

1. Seven days of real `extra-weekly.timer` fires without silent gaps  
2. Merge PR to main with CI green  
3. DOD ACCEPTED only for items with evidence on main  
