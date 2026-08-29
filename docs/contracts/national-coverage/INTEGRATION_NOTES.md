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
- Not a second crawler. The live census reuses the PNCP catalog, source-wide
  contracts crawler checkpoints, and existing national-coverage identity.

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

`PARTIAL_RESIDUAL` — the official catalog is inventoried and the local queue is
resumable, but the 2026-08-29 observation still has four uncovered source days
and no official publishing-unit enumerator. See
`docs/ops/session-2026-08-29-national-census/evidence.json`.
