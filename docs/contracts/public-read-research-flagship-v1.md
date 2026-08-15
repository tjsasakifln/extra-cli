# `public_read_v1` research flagship contract

Version: `v1.1.0` (additive on `public_read_v1` `v1.0.0`)
Schema: `public-read-research-flagship/1.0`
Machine-readable twin: [`public-read-research-flagship-v1.json`](public-read-research-flagship-v1.json)

Consumer: `web-cfg / flagship research` (`tjsasakifln/web-cfg#65`, PR `#73`)
Wedge: contracts / prices / margin-defense — volume and ticket of the **integral nominal BRL contract**, not unit price.

## Boundary

This is a SELECT-only, versioned family inside `public_read_v1`. It is not a
generic API, browser API, exploratory endpoint, or second DataLake. The
PostgreSQL role `smartlic_public_reader` remains SELECT-only.

The shipped consumer path is the deterministic export:

```bash
python3 -m scripts.public_read export-research --fixture PATH --out DIR
python3 -m scripts.public_read health --artifact DIR/research-export.json
```

web-cfg knows it may publish a national claim only when
`claim.national_claim_allowed` is `true` on that artifact (and on
`public_read_v1.research_claim_gate` after an optional apply).

## Grain, keys, sources

| Field | Contract |
|---|---|
| Grain | `competence × geography_kind × geography_code × archetype_id` |
| Keys | those four fields; `series_key` is their `|`-joined form |
| Source families | `public_read_v1.contracts`, `canonical_public_observations`, `national_universe/1.0` |
| Value semantics | integral nominal BRL; P25/median/P75 nearest-rank; never m² or deflated price |
| Temporal / geographic denominator | #302 publishing-org universe via `reconcile_partitions`; `nacional_completo` only when every partition closes `FOUND` or `ZERO_CONFIRMED` with evidence |
| `as_of` | input snapshot cutoff, never wall-clock |
| Freshness | `contracts-freshness-slo-v1` publication layer, 48h |
| Completeness | `COMPLETE` / `INCOMPLETE` / `UNKNOWN` |
| Provenance | source + record + lineage + catalog/reconciliation/content hashes |
| UNKNOWN / `reason_codes` | listed in the JSON twin; UNKNOWN stays UNKNOWN |
| Query budget | `public_read_v1.query_budgets` families `research_flagship_series`, `research_claim_gate`, `research_health` |

Forbidden denominators: Extra's commercial 1.093-entity universe; any 4-UF
slice claimed as BR; any recorte without `nacional_completo`.

## National claim gate

`national_claim_allowed` is true **only** when all of the following hold:

1. `reconcile_partitions` returns `nacional_completo=true`
2. no partition is missing, `BLOCKED`, or `FAILED`
3. publication freshness is within SLO
4. no series row is UNKNOWN
5. no unresolved duplicated source lineage
6. Extra 1093 was not used as the denominator

Otherwise the export refuses geography `BR` and must not carry publishable
"Brasil"/"nacional" claim language. `nacional_completo` and
`national_claim_allowed` remain gate fields, not published claims.

## Additive `public_read_v1` families (`v1.1.0`)

| Family | Role |
|---|---|
| `research_flagship_series` | chart/research cells |
| `research_claim_gate` | singleton eligibility |
| `research_health` | freshness, coverage, consumer errors |

No v1.0.0 column is removed or renamed. Migration
`094_public_intelligence_research_models.sql` was used because 094 was free on
`origin/main` at `42166330` after fetch. No other front of this package uses 094.

## Honesty

Fixtures and a versioned export do **not** prove a live national PNCP census or
`VPS_OPERATIONAL`. A publicable national research remains `NEEDS_DATA` until a
live #302 denominator actually closes.
