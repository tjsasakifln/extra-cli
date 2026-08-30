# ADR-038 — National census entity-authority boundary

**Status:** Proposed
**Date:** 2026-08-29
**Issue:** extra-cli#302
**PR:** extra-cli#525

## Context

The PNCP organization endpoint returns an unwrapped array of publishing
organizations, but does not declare a total and does not enumerate publishing
units. The existing contracts crawler checkpoints close publication-date
windows for a source-wide query. They contain no request or pagination proof
for each organization.

Treating aggregate completion plus absence from the local corpus as an
entity-level `ZERO_CONFIRMED` would violate the national-claims contract and
ADR-021: no request for that entity occurred, and the official denominator is
not complete at the requested unit grain.

## Decision

1. The census queue is an inventory/reconciliation mechanism, not an
   entity-query crawler.
2. A catalog organization present in the bound corpus snapshot is `FOUND`.
   An absent organization remains `BLOCKED`; source-wide completion never
   promotes it to `ZERO_CONFIRMED` or entity-level `FAILED`.
3. Only source-wide checkpoints explicitly bound to
   `historical_contracts` and `query_kind=publication` may describe the corpus
   window. Missing or update-date semantics fail closed.
4. Checkpoint terminal states are rederived from the hashed catalog/corpus
   inputs on resume. Persisted state cannot grant authority by itself.
5. Corpus aggregation fails if any buyer identity cannot map to a 14-digit
   CNPJ; invalid rows are reported, never filtered out before reconciliation.
6. The catalog records transport-body integrity separately from denominator
   completeness. A missing declared total remains an authorization blocker.
7. `expected_units=NULL` is the truthful persistence value while PNCP does not
   enumerate publishing units. Migration 102 aligns PostgreSQL with that
   contract; rollback refuses to invent values.
8. Live evidence is not committed as completion proof unless it is reproduced
   on the exact PR HEAD and all required gates are green. This PR does not close
   #302 and does not authorize indexation.

## Consequences

- The queue remains deterministic, resumable and bounded without creating one
  HTTP request per catalog organization.
- A fully processed source-wide queue can still be `PARTIAL` with many
  `BLOCKED` partitions. That is the intended fail-closed result.
- A future national authorization needs a complete official denominator,
  publishing-unit enumeration, and entity-scoped positive/negative evidence.
- Legacy checkpoints without explicit query semantics must be regenerated or
  migrated by their producing crawler; operators cannot annotate them at census
  consumption time.

## Rejected alternatives

| Alternative | Reason rejected |
|---|---|
| Infer zero from absence in a closed aggregate date window | No entity-scoped request or negative pagination evidence exists. |
| Assume one publishing unit per organization | Invents an official denominator and conflicts with the PNCP response grain. |
| Silently discard invalid buyer identities | Makes corpus reconciliation look more complete than the stored source rows. |
| Trust checkpoint terminal lists after input-hash match | A forged or corrupted status could promote authority without rederivation. |

## Verification

- `tests/national_coverage/test_census.py`
- `tests/national_coverage/test_adversarial_hardening.py`
- `tests/national_coverage/test_persist.py`
- `docs/ops/national-census-operation.md`
