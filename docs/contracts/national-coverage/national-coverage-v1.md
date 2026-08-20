# National coverage contract `national-coverage/1.0`

Versioned publishing-org denominator plus stock reconciliation of the current
contract corpus. Facts for the editorial / SEO / research gate.

This tree does **not** replace the six-state `national-claims/1.0` arbiter.
It does **not** recensus the live PNCP catalog (~98k partitions). It does
**not** authorize indexation.

Machine-readable twin: [`national-coverage-v1.json`](national-coverage-v1.json)
Integration: [`INTEGRATION_NOTES.md`](INTEGRATION_NOTES.md)

## Verdict

Exactly one of:

`NATIONAL_CLAIM_AUTHORIZED` · `PARTIAL` · `NOT_MEASURED` · `BLOCKED`

`national_claim_authorized` is true only when every expected partition of a
**valid official** denominator closed `FOUND` or `ZERO_CONFIRMED` with
evidence, the request geography is national, and Extra 1.093 was not used.

`PARTIAL`, `NOT_MEASURED` and `BLOCKED` never set the boolean true.
Absence of consultation is `BLOCKED` / `not_consulted_this_run`, never
`ZERO_CONFIRMED`.

## Two denominators

| Kind | Role |
|---|---|
| `OFFICIAL` | PNCP `/api/pncp/v1/orgaos` (or another official enumerator). Only legal national denominator. |
| `OBSERVED_CORPUS` | Publishers present in the current corpus snapshot. Labeled `OBSERVED_CORPUS`. Cannot authorize a national claim. |

When the official enumerator is unavailable, the official denominator is
`BLOCKED` with a cause and the observed-corpus companion is still emitted.

## Required metadata

Each universe version carries `national_universe_id`, schema/method version,
official source URL or identifier, competence/cutoff, `retrieved_at` and
`as_of`, raw/source hash, inclusion/exclusion, grain, expected vs observed
partitions, expected/queried/closed counts, missingness, relation to a
corpus snapshot, verdict, reason codes, owner and next refresh.

Same source + catalog hash + policy reproduces the same `universe_id` and
counts. `content_hash` excludes wall-clock, including nested `retrieved_at`.

## Corpus snapshot

The current stock is identified by **publisher aggregates** (SELECT
`GROUP BY orgao_cnpj, uf`). The ~4.5M contracts are not rewritten.
Mapping statuses: `MAPPED` · `UNMAPPED` · `DUPLICATE` · `CONFLICT` · `ALIAS`.
Stock coverage (found in stock) is separate from freshness coverage
(last_seen inside the window).

## Consumer

SELECT-only view `national_coverage_consumer_v1`. Fields: requested
geography/period/source/grain, `universe_id`, expected/closed partitions,
`coverage_pct` only when the official denominator is valid (otherwise
null), freshness, missingness, `national_claim_authorized`, reason codes,
limitations, provenance/version/hash.

`coverage_pct` is a closed/expected measurement. It is not authorization.

## CLI

```bash
python3 -m scripts.national_coverage evaluate \
  --input docs/contracts/national-coverage/fixtures/official-partial.json \
  --out exports/national-coverage/official-partial.json
```

## Honesty

Fixtures and in-memory catalogs do not prove a live PNCP census. extra-cli#302
stays open until every official publishing-org partition is consulted with
evidence. Extra's 1.093 monitored entes remain a commercial universe.
