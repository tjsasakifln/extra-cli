# Analyze report — 004 vs 001–003

## Spec inventory

| Spec | Theme | Overlap with 004 |
|------|-------|------------------|
| 001 dual-capability-coverage-truth | Dual open_tenders / historical_contracts denominators | Must not inflate; 060 views stay analytical |
| 002 historical-contracts-operational-coverage | 3y contracts lake + coverage | Data source for A–D aggregates |
| 003 open-tenders-operational-decision-cycle | Weekly E + dual open_tenders | E evidence reuse; weekly path |
| 004 (this) | Live consulting pack A–E isolated | Consumes 001–003 outputs; does not re-open dual formula |

## Consistency

- PR #121 labeled its national intel as “spec 003” — **conflict resolved** by creating **004** on main (main 003 = open-tenders).
- Migration 059 on main = coverage unique; PR #121 059 renumbered to **060**.
- Deliverable modules on main are schema/fixture-first; 004 adds **live_consulting_pack** real-path orchestrator without replacing audits.

## Gaps closed by 004

- Full-population aggregates (not silent 5k sample as universe)
- Monthly monitor live-isolated path
- Package PDF/Excel from same run_id on real data
- Isolation gate for parallel soak campaigns

## Residual risks

- Human Tiago acceptance external
- Dual coverage live re-measure still soak-bound
- Entity universe 1093 may be empty in isolated DB (UF=SC filter used)
