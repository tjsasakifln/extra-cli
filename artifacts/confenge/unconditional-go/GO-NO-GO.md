# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T04:10:11Z`

## Terminal state (honest)

**`EXTERNAL_BLOCKER_REQUIRES_TIAGO`** — human review of stratified clean sample is the sole remaining non-automatable gate for lead-level HUMAN_REVIEW_APPROVED.

Engineering blockers from the objective (merge/deploy/provenance/taint/cleanup/target-fit module) have been eliminated or are in final CI/merge:

| Gate | Status |
|------|--------|
| Provenance fail-closed gates (extra-cli) | DONE — PR #213 |
| Warmbly import/CanEnroll taint | DONE — PR #35 |
| Contaminated 62 cohort invalidated | DONE — INVALIDATED_REASON=PROVENANCE_CONTAMINATION |
| demo00* sendable | **0** (9 blocked in production) |
| Clean cohort ≥50 companies | **53** |
| First-50 audit counters all 0 | **True** |
| Target-fit runtime HEALTHY (SHADOW) | DONE on host-of-record |
| Target-fit continuous merge #212 | CI fix pushed (conn join) |
| Dual SHA identity on main | pending PR merges to main + deploy pin |
| Human review 10–15 sample | **REQUIRES TIAGO** — see HUMAN-REVIEW-SAMPLE.md |

## Do NOT reuse

Historical contaminated evidence: ESR=62, WRONG_CONTACT=0, NEW-30-HUMAN-REVIEW, prior GO claims.

## Resume after human review

1. Fill decisions in `artifacts/confenge/unconditional-go/human-review-decisions.jsonl`
2. Re-export clean feed excluding non-approved if policy requires
3. Import to Warmbly with kill switch ENGAGED
4. Operator self-smoke only

Then re-evaluate §21 vector for `GO_FOR_REAL_CONFENGE_EMAIL_PILOT`.
