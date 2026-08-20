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
`facts["national_claim_allowed"]` tracks `national_claim_authorized`.

## What this is not

- Not `scripts.national_claims.decide` (six-state arbiter stays).
- Not `scripts.contract_comparables` (PR #435).
- Not `scripts.coverage.promote_or_defer` (PR #413).
- Not a live 98k PNCP census. extra-cli#302 remains open.

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

`PARTIAL_RESIDUAL` — official enumerator contract and observed-corpus
companion exist; live publishing-org census is not closed.
