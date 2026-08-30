# National publishing-org census operation

This is the operator runbook for blocker #302. The operation consumes the
official PNCP organization catalog once and reconciles its deterministic CNPJ
queue against publisher aggregates already collected by the canonical PNCP
contracts crawler.

## Truth boundary

- Denominator: every unique CNPJ returned by the official
  `https://pncp.gov.br/api/pncp/v1/orgaos` response at the recorded retrieval
  time. Active and inactive counts are reported; neither is silently dropped.
- Grain: `publishing_org`. The endpoint does not enumerate units, so
  `unit_count=null` and `publishing_unit_denominator_not_enumerated` remain in
  limitations.
- `FOUND`: the catalog CNPJ occurs in the bounded corpus snapshot.
- `ZERO_CONFIRMED`: reserved for future evidence from an entity-scoped request
  whose pagination and persistence reconcile. This source-wide operation never
  emits it.
- `FAILED`: reserved for a typed entity-scoped query failure. A source-wide
  failure remains a global reason code and does not pretend an entity was queried.
- `BLOCKED`: the CNPJ is absent from the aggregate corpus, source days are
  incomplete, or the queue slice has not reached the partition. `BLOCKED` is
  never promoted by aggregate absence.

The 1,093 Extra commercial entities are rejected by the existing policy and
never enter these inputs.

## Load safety

`fetch-catalog` performs one bounded GET. It uses the shared HTTP resilience
policy for 429/5xx/timeout classification, finite exponential backoff, the
persistent circuit breaker, and a 128 MiB response ceiling. Raw and manifest
are published in the same directory as a content-addressed bundle: the new raw
version and directory entry are durable before the manifest atomically advances. Failed refreshes leave the prior
last-known-good manifest/raw pair and its retrieval timestamp unchanged.

The endpoint returns an unwrapped array without a declared total. A well-formed
HTTP body proves transport integrity, not catalog completeness; the report
therefore carries `official_catalog_total_not_declared` and cannot authorize a
national claim from this catalog alone.

No HTTP request is made per partition. Local partition processing is
single-worker by design. The checkpoint has an exclusive non-blocking file
claim, atomic replacement, a sorted-CNPJ cursor, compact terminal lists, and an
input fingerprint over catalog/corpus/window hashes. Input drift or corruption
fails closed instead of restarting or mixing runs.

## Replay and restart

Use `--max-partitions N` for a bounded slice. Running the same command again
with the same checkpoint resumes at `next_index`; terminal entries are not
reprocessed. A changed catalog, corpus, period, or window manifest produces
`checkpoint_input_hash_mismatch` and requires a new checkpoint path.

Heavy raw/catalog/checkpoint/report artifacts remain under the operational data
directory or Actions artifacts. Commit only compact hashes and summaries under
the generated-artifacts policy.

```bash
python3 -m scripts.national_coverage fetch-catalog \
  --out-raw /srv/extra/census/catalog.json \
  --out-manifest /srv/extra/census/catalog.manifest.json \
  --competence contracts-2023-07-20_2026-08-28 \
  --cutoff 2026-08-28

python3 -m scripts.national_coverage snapshot-corpus \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --period-start 2023-07-20 --period-end-exclusive 2026-08-29 \
  --out /srv/extra/census/corpus.json

python3 -m scripts.national_coverage census \
  --catalog-manifest /srv/extra/census/catalog.manifest.json \
  --corpus-json /srv/extra/census/corpus.json \
  --window-checkpoint /srv/extra/checkpoints/contracts_full.json \
  --checkpoint /srv/extra/census/operation.checkpoint.json \
  --out /srv/extra/census/report.json
```

The acquisition commands stamp `retrieved_at` themselves. The replay command
does not accept a timestamp override: catalog and corpus timestamps are bound
to their manifests/hashes, so replay cannot renew freshness.

Every `--window-checkpoint` must explicitly bind
`meta.query_kind=publication` and `meta.capability=historical_contracts`.
Legacy checkpoints without query semantics and update-date checkpoints are
rejected; they cannot prove a publication-date window.

## Consumer handoff

The report contains the existing `national-coverage/1.0` consumer plus:

- `national_universe_id`, source, cutoff, `as_of`, method/schema versions;
- raw/catalog/reconciliation hashes;
- expected/queried/closed and status counts;
- freshness, reason codes, provenance, and limitations;
- `nacional_completo`, `national_claim_allowed`, and
  `national_claim_authorized` aliases.

All three booleans remain false for this source-wide operation. A later producer
would need a complete official denominator, publishing-unit enumeration and
entity-scoped `FOUND|ZERO_CONFIRMED` evidence before the existing gate could
authorize a national claim. This operation never authorizes indexation.

## Rollback

Stop the command and preserve its checkpoint for diagnosis. Removing the new
operational files disables this producer; source contract rows and the
public-read-v1 view are not mutated. Migration 102 only allows `expected_units`
to remain SQL `NULL` when the official endpoint does not enumerate units; its
rollback fails closed while such rows exist rather than inventing a count.
