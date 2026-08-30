# Integration notes — national coverage / extra-cli#400

Owner tree: `scripts/national_coverage/**`, `docs/contracts/national-coverage/**`.

## What this is

Coverage denominator + corpus stock reconciliation + consumer facts for the
editorial gate. extra-cli#400 may **read** the SELECT-only adapter:

```python
from scripts.national_coverage.adapters import public_read_claim_facts
facts = public_read_claim_facts(payload["consumer"])
```

`facts["indexation_authorized"]` is always `false`.
`facts["national_claim_allowed"]` and `facts["nacional_completo"]` track
`national_claim_authorized`. The handoff also includes source, cutoff, `as_of`,
method version, catalog hash, and reconciliation hash.

## What this is not

- Not `scripts.national_claims.decide` (six-state arbiter stays).
- Not `scripts.contract_comparables` (PR #435).
- Not `scripts.coverage.promote_or_defer` (PR #413).
- Not a second crawler. The live census reuses the PNCP catalog, publication-date
  source-wide contracts checkpoints, and existing national-coverage identity.
- Not entity evidence. Aggregate windows never prove an entity-level zero or
  authorize a national claim.

## Consumer SELECT

```sql
SELECT requested_geography, requested_period, requested_source, requested_grain,
       universe_id, expected_partitions, closed_partitions, coverage_pct,
       national_claim_authorized, verdict, reason_codes, limitations,
       provenance, content_hash
FROM public.national_coverage_consumer_v1
WHERE universe_id = :universe_id;
```

`coverage_pct` is null unless the official denominator is valid.

## Residual on #302

`PARTIAL_RESIDUAL` — the official catalog can be inventoried and the local queue
is resumable, but source-wide absence is not entity evidence, the catalog
response declares no total, and no official publishing-unit enumerator is
available. There is no committed live observation or exact-HEAD completion
proof; #302 remains open.
