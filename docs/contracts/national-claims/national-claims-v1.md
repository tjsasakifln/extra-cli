# National claims contract `national-claims/1.0`

Unique inbound arbiter for national / scoped public claims. Goals 01–03
simulate this payload by fixture. They do not import candidate, comparables
or read-model engines.

Policy: `national-claims-gate/1.0`
Machine-readable twin: [`national-claims-v1.json`](national-claims-v1.json)
Integration: [`INTEGRATION_NOTES.md`](INTEGRATION_NOTES.md)

## Decide

Given claim scope, período, fonte(s), tipologia, geografia, snapshot/cutoff
and policy version — plus the versioned universe, partition records,
classified evidence, freshness and optional prior last-known-good — the
shipped gate returns **exactly one** of:

`AUTHORIZED` · `AUTHORIZED_WITH_LIMITATIONS` · `NEEDS_DATA` · `STALE` · `BLOCKED` · `FAILED`

A national / “nacional completo” / `AUTHORIZED` outcome is refused when:

- the versioned national denominator is incomplete;
- Extra 1.093 / ICP-commercial / observed-corpus is used as that denominator;
- completeness is inferred from row count.

A claim limited by geography or period may be `AUTHORIZED_WITH_LIMITATIONS`
and is **never** labeled national (`nacional_completo=false`).

## Four universes

None substitutes another.

| Kind | Role |
|---|---|
| `national` | Official publishing-org catalog (#302). Only legal national denominator. |
| `icp_commercial` | Commercial ICP universe. |
| `extra_1093_monitored` | Extra's 1.093 monitored entes (`sc_public_entities.raio_200km`). |
| `observed_corpus` | Rows present in the snapshot. |

Each national version carries `national_universe_id`, official source, cutoff,
hash, competência, expected órgãos/unidades, expected partitions,
inclusion/exclusion, version changes, owner and review cadence.

Replaying the same raws/hashes reproduces id, hash, counts and reconciliation.

## Partitions

Statuses: `FOUND` · `ZERO_CONFIRMED` · `BLOCKED` · `FAILED` · `NOT_APPLICABLE` · `UNKNOWN`

- Absence of execution is `UNKNOWN`, never zero.
- `ZERO_CONFIRMED` requires complete request + pagination + evidence ref.
- Legacy `BLOCKED`/`not_consulted_this_run` is remapped to `UNKNOWN`.
- Counts close: expected vs attempted vs closed.

## #350 identity

Source-wide / aggregated evidence is stored in
`national_claims_aggregate_evidence`. It is never silently dropped and never
proves entity or dual coverage. A national claim whose partitions all close
but whose evidence is source-wide only is `NEEDS_DATA`, not `AUTHORIZED`.
Unmappable identity stays fail-closed with `unmappable_evidence_cannot_drop`.

## Freshness and last-known-good

Publication SLO is `contracts-freshness-slo-v1` (48h). Breach → `STALE`.

Last-known-good:

- exists only after a prior `AUTHORIZED`;
- has explicit expiration (default 48h);
- is invalidated by a material universe/method/source change;
- never authorizes the **current** claim from a stale payload;
- consumer view is `current` | `lkg` | `blocked`;
- prior evidence is never deleted.

## Consumer payload (minimum)

`claim_id`/`scope`, `national_universe_id`/`catalog_hash`, numerator/denominator,
partitions expected/closed, coverage pct and missingness, freshness/`as_of`,
source/method/policy versions, `authorization_state`, limitations/reason codes,
`lkg_ref`, invalidation triggers, producer SHA, `content_hash`.

`content_hash` excludes wall-clock, producer SHA and report cost so two
evaluations of the same fixture match.

## CLI

```bash
python3 -m scripts.national_claims evaluate \
  --input docs/contracts/national-claims/fixtures/needs-data.json \
  --out reports/national_claims/needs-data.json \
  --report reports/national_claims/needs-data.md --format md
```

## Honesty

Fixtures do not prove a live PNCP census. #302 and #350 stay open until the
official catalog (~98k partitions) is actually consulted. This contract is
the arbiter; `scripts.public_read.claim_gate` remains a boolean consumer.
