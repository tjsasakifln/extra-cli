# Handoff — national census / PR #525

**Date:** 2026-08-29
**Issue:** #302 remains open
**Decision:** ADR-038 (proposed)

## Delivered on the branch

- bounded, content-addressed PNCP organization-catalog acquisition;
- deterministic local queue with exclusive claim and resumable checkpoint;
- corpus snapshot bound to publication period and exact aggregate hash;
- fail-closed checkpoint semantics and terminal-state rederivation;
- nullable persistence for the unknown publishing-unit denominator.
- one audit timestamp per projected contracts-evidence event and monotonic
  circuit-breaker cooldowns, so host clock corrections cannot create false
  future evidence or prolong an OPEN state.

## Authority boundary

This producer never turns source-wide absence into entity-level
`ZERO_CONFIRMED`. Absent organizations remain `BLOCKED`; unknown catalog total
and publishing-unit denominator also block national authorization. No live
completion evidence is committed for this PR.

## Verification and remaining gates

- national-coverage tests: 56 passed, one pre-existing mode skip;
- real PostgreSQL suite: 134 passed in normal order and 134 in reverse order,
  each on a newly migrated and seeded database;
- canonical full suite: 6,274 passed and 140 pre-existing skips; one unrelated
  commercial freeze test was excluded because it also fails at the PR base SHA;
- local golden path completed migrations, seeds, crawlers and reports, then
  correctly failed the strict freshness gate: PNCP/contracts evidence is absent
  and both capability numerators remain zero.

Exact-HEAD CI, `main` acceptance and fresh entity-scoped operational evidence
remain required. A green code CI does not close issue #302 or authorize an
operational coverage claim.

## Operator next action

1. Generate a fresh contracts checkpoint that explicitly records
   `meta.capability=historical_contracts` and `meta.query_kind=publication`.
2. Run the catalog, corpus and census commands from
   `docs/ops/national-census-operation.md` on an isolated operational path.
3. Retain raw reports as an Actions/operations artifact and bind them to the
   exact deployed SHA; do not promote #302 from source-wide evidence.
4. Define a separate official publishing-unit enumerator and entity-scoped
   evidence method before requesting national authorization.

## Rollback

Revert the producer code and remove its operational files. Migration 102 can be
rolled back only after all `expected_units IS NULL` rows are removed by an
explicit data decision; the rollback deliberately raises otherwise.
