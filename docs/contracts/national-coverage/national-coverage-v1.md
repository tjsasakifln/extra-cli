# National coverage contract `national-coverage/1.0`

Versioned publishing-org denominator plus stock reconciliation of the current
contract corpus. Facts for the editorial / SEO / research gate.

This tree does **not** replace the six-state `national-claims/1.0` arbiter and
does **not** authorize indexation. The `census` operation inventories the live
PNCP catalog and reconciles it from existing source-wide crawler checkpoints;
it does not issue one request per publishing organization.

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

`national_claim_allowed` and `nacional_completo` are explicit aliases of the
authorization boolean for consumer handoff. `reconciliation_hash` is included
at the top level and in provenance.

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

Source freshness is separate again: a fully closed last-known-good cutoff that
is older than the configured window returns `source_cutoff_stale`; replay never
changes `retrieved_at`, cutoff, or freshness.

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

The non-interactive live operation has three stages:

```bash
python3 -m scripts.national_coverage fetch-catalog \
  --competence contracts-2026 \
  --cutoff 2026-08-28 \
  --out-raw /var/lib/extra-consultoria/national-census/catalog.json \
  --out-manifest /var/lib/extra-consultoria/national-census/catalog.manifest.json

python3 -m scripts.national_coverage snapshot-corpus \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --period-start 2023-07-20 \
  --period-end-exclusive 2026-08-29 \
  --out /var/lib/extra-consultoria/national-census/corpus.json

python3 -m scripts.national_coverage census \
  --catalog-manifest /var/lib/extra-consultoria/national-census/catalog.manifest.json \
  --corpus-json /var/lib/extra-consultoria/national-census/corpus.json \
  --window-checkpoint /var/lib/extra-consultoria/checkpoints/contracts/contracts_full.json \
  --checkpoint /var/lib/extra-consultoria/national-census/census.checkpoint.json \
  --out /var/lib/extra-consultoria/national-census/census.report.json
```

Additional `--window-checkpoint` arguments union historical/canary campaigns by
day. Completed windows take precedence over stale cumulative failure counters.
The checkpoint is atomic, exclusively claimed, ordered by normalized CNPJ, and
resumable. Parallel HTTP partition crawling is deliberately absent: the single
catalog GET plus source-wide crawler evidence is the bounded-load path.

## Honesty

Fixtures and in-memory catalogs do not prove a live PNCP census. extra-cli#302
stays open while any official publishing-org partition is `BLOCKED`/`FAILED`
or the requested unit grain is not enumerated. Extra's 1.093 monitored entes
remain a commercial universe.
