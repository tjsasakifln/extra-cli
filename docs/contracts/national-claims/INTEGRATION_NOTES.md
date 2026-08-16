# INTEGRATION_NOTES — national claims gate → #400 / #414 / #415

Owner tree: `scripts/national_claims/**`, `docs/contracts/national-claims/**`.
Do not edit candidate / comparables / read-model engines from this package.

## How Goal 03 (Market Answer / research, #400) consumes this

Evaluate a fixture or a built request:

```python
from scripts.national_claims import decide, load_request

payload = decide(load_request("docs/contracts/national-claims/fixtures/needs-data.json"))
if payload["authorization_state"] != "AUTHORIZED":
    # refuse "nacional" / "Brasil completo" language
    ...
if payload["consumer_view"] == "lkg":
    # show last-known-good as historical, never as the current claim
    ...
```

Boolean consumers (`scripts.public_read.claim_gate.national_claim_allowed`)
must treat `authorization_state == "AUTHORIZED"` as the only true national
authorization. A fixture `true` on the old boolean gate is not live national
authority.

Required fields for a Market Answer / research label:

- `authorization_state`
- `nacional_completo` (false unless AUTHORIZED national)
- `consumer_view` (`current` | `lkg` | `blocked`)
- `reason_codes` / `limitations`
- `national_universe_id` + `catalog_hash`
- `content_hash`

## How Goals 01 / 02 (#414 publication candidate, #415 comparables) consume this

Use the same payload to **label corpus**, not to invent coverage:

| authorization_state | Label |
|---|---|
| AUTHORIZED | corpus may carry `national` only for the versioned universe/hash |
| AUTHORIZED_WITH_LIMITATIONS | label the geo/period scope; never `national` |
| NEEDS_DATA | `coverage_unknown` / `needs_data` |
| STALE | `stale`; optional LKG ref, not current authority |
| BLOCKED | `blocked` + reason codes |
| FAILED | `failed` + reason codes |

Do not treat Extra 1.093, ICP, or snapshot row count as the national
denominator when labeling.

## #350

Source-wide evidence lands in `national_claims_aggregate_evidence` and in
`payload.identity.source_wide`. It does not increment dual-coverage
numerators. Unmappable rows fail closed (`unmappable_evidence_cannot_drop`).

## Live census

This package does **not** close #302 or #350. A live `AUTHORIZED` national
claim requires the official PNCP publishing-org catalog to close every
partition. Current live universe still has ~98k partitions unconsulted.

Live smoke (when `LOCAL_DATALAKE_DSN` is reachable):

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m scripts.national_claims evaluate \
  --input docs/contracts/national-claims/fixtures/needs-data.json \
  --out reports/national_claims/live-smoke.json
```
