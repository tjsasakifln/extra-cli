# Analyze report — Spec 002

**Date**: 2026-07-23  
**Analyst**: campaign coordinator (HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01)

## Cross-artifact consistency

| Artifact | Status | Notes |
|----------|--------|-------|
| spec.md | Updated | VPS/cutover/soak in scope; host of record Netcup |
| plan.md | Updated | Foundation → backfill → cutover → ops → soak → DOD |
| tasks.md | Reconciled | Removed false `[x]` for incomplete backfill/projection |
| checklists/requirements.md | Updated | Living gates |
| STATUS.md | Stale mid-backfill | Still useful; checkpoint now ~28/37 |
| handoff Netcup | Valid | Writer local; VPS snapshot 26/37 drift |
| Spec 001 | Read-only dep | Dual spine preserved |
| DOD | Not advanced | No ACCEPT this wave without main+CI+evidence |
| ADR-018–021, 028–030 | Preserved | No dual reopen |
| ADR-007/008, README | Divergent | Must converge (T0d) |

## Defects confirmed in code/runtime

1. success_zero fabricable by flags → **fixed** (proof required)
2. weekly strict test missing contracts run → **fixed**
3. export/restore soft-fail → **fixed** (fail-closed)
4. validate_systemd incomplete → **fixed**
5. systemd units broken patterns → **fixed in repo**; host apply pending
6. health_check hard-required storage-box → **optional unless REQUIRE_STORAGE_BOX=1**
7. origin remote still extra-consultoria vs extra-cli
8. migration 059 collision with PR #121 — precedence this campaign

## Coverage measurement honesty

Dual snapshot 2026-07-22: coverage 0%, applicability_unknown 147 under old policy stamp — **not** operational PASS. Must re-measure after proof-gated projection.

## Open risks

- Backfill incomplete (28/37); PNCP flakiness
- Off-site backup credentials
- Soak wall-clock 7 days
