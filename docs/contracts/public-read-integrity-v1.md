# public-read-integrity/1.0

Fail-closed producer for **CEIS** and **CNEP** only (Portal da Transparência /
CGU). Future consumer: `web-cfg#156`. This contract is not a landing page,
index grant, or publication authority.

Machine-readable twin: [`public-read-integrity-v1.json`](public-read-integrity-v1.json)
Payload schema: [`public-read-integrity-v1.schema.json`](public-read-integrity-v1.schema.json)

## Decide

Given a CNPJ and injectable page/error transport, the producer:

1. validates and normalizes the CNPJ (14 digits + check digits);
2. runs **separate** CEIS and CNEP adapters with bounded retry;
3. paginates each source until a **successful terminal page** (typically an
   empty page). A failed request is never treated as the end of the stream.
   Hitting the safety page cap is incomplete;
4. normalizes records (keeps originals), then applies deterministic dedupe;
5. attaches provenance, coverage, freshness/TTL;
6. returns exactly one aggregate state:

`MATCHES_FOUND` · `NO_MATCH_CONFIRMED` · `PARTIAL` · `UNKNOWN`

The same four states apply per contracted source.

## Fail-closed rules

- `NO_MATCH_CONFIRMED` only when **every** contracted source ran, **every**
  page completed (successful terminal page), and the normalized/deduped
  result is empty.
- Timeout, exhausted 429 retry, 5xx, schema drift, parse error, incomplete
  pagination, missing source, or expired cache **never** yield
  `NO_MATCH_CONFIRMED`. They yield `PARTIAL` or `UNKNOWN`.
- Matches from one complete source may appear while the aggregate is
  `PARTIAL` or `UNKNOWN`.
- A missing value is not a negative fact.
- Uncontracted cadastros (CEPIM, CEAF, TCU, CNJ, SICAF, …) do not enter the
  conclusion.
- Stale or expired cache is never labeled `current`.
- Invalid CNPJ does not become `NO_MATCH_CONFIRMED` (it is `UNKNOWN`).
- `scripts.crawl.sanctions` is not an authority for this contract (fail-open
  empty list on error; logs full CNPJ).

## Payload (minimum)

- `schema` / `schema_version` = `public-read-integrity/1.0`
- `query_id` (deterministic)
- `queried_cnpj` (normalized, **private payload only**)
- `checked_at`, `as_of`, `expires_at`
- `freshness` with policy, TTL, `status` (`current` | `stale` | `expired`),
  `is_current`
- per source (`CEIS`, `CNEP`): `source_id`, official URL, authority, `status`,
  `pages_expected`, `pages_fetched`, `coverage_complete`, counts, reason
  codes, `as_of`
- `records`: official identifier, type, authority, start/end when present,
  observed status, source URL, capture timestamp, `original`
- `limitations`, `reason_codes`
- `not_legal_conclusion` = `true`
- `content_hash`, `producer_version`

No indexing fields, commercial/legal score, or recommendation fields.

## Freshness / TTL

Default TTL is 86400 seconds (`public-read-integrity-ttl/1.0`). Replay from
fixtures freezes `checked_at` / `as_of` / `expires_at` so two runs of the
same fixture produce the same `content_hash`. Expired cache is `expired`
and `is_current=false`.

## Honesty

Copy describes only consulted sources, instant, coverage and observed
occurrences. It never certifies a clean record, fitness, or absence of risk.

Full CNPJ appears only in the private payload. Logs, telemetry, public
fixtures and `exports/public-integrity/**` redact it.

## CLI

```bash
python3 -m scripts.public_integrity replay \
  --fixture tests/public_integrity/fixtures/matches.json \
  --cnpj DIGITS --out payload.json
```

Default CI path is offline fixture replay. Live Portal da Transparência is
out of band (`--live`) and is not the merge bar.

## Consumer

`exports/public-integrity/` holds a SELECT-only read-model fixture labeled
for `web-cfg#156`: `no_index`, no publication authority, not live. No
consumer page ships in this slice.
