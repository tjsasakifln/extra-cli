# CONFENGE ↔ Warmbly bridge — local operations

Native producer of `confenge.outreach.v1` and optional HMAC receptor for
`confenge.outcome.v1`. Closes the integration gap between **extra-cli**
(intelligence) and **Warmbly** (execution / copy / send).

## What this is / is not

| Is | Is not |
| --- | --- |
| Path-based export from the full decision universe, target-fit snapshot, intelligence and contacts JSONL | A send-ready cohort exporter |
| Chunked feed with cursor, hashes, manifest, resume | One monolithic unusable JSON dump |
| Messaging **context** for Warmbly to draft copy | Final email/WhatsApp copy |
| Outcome webhook into Decision & Outcome Memory | A second parallel outcome ledger |
| Fail-closed on missing inputs | Silent shallow outreach fabrication |

## Generate feed

From repo root (with fixtures or real pipeline outputs):

```bash
python3 -m scripts.warmbly_bridge export-outreach \
  --universe scripts/warmbly_bridge/fixtures/universe.jsonl \
  --account-intelligence scripts/warmbly_bridge/fixtures/account_intelligence.jsonl \
  --contacts scripts/warmbly_bridge/fixtures/contacts.jsonl \
  --target-fit-snapshot /path/to/full-target-fit-snapshot.jsonl \
  --expected-universe-count 12345 \
  --out /tmp/confenge-outreach-out

# Smoke only. Its manifest has coverage_complete=false and must not be imported
# as an authoritative account snapshot:
python3 -m scripts.warmbly_bridge export-outreach \
  --universe ... --account-intelligence ... --contacts ... \
  --out /tmp/confenge-outreach-out \
  --limit 20 \
  --max-leads-per-chunk 50 \
  --max-bytes-per-chunk 512000
```

**Outputs under `--out`:**

- `manifest.json` — run metadata, snapshot hash, per-chunk content hashes
- `chunk_0000.json`, `chunk_0001.json`, … — each a full `confenge.outreach.v1` document

Re-running with the **same inputs** reuses `generated_at` from the prior
manifest (when `snapshot_hash` matches) and leaves chunk files `unchanged`
when content hashes match (resume / idempotency).

Missing any of `--universe`, `--account-intelligence`, or `--contacts`
exits non-zero with an explicit error — no shallow feed is written.

## Authoritative target-fit snapshot

Production must pass `--target-fit-snapshot` and the reconciled
`--expected-universe-count`. The universe contains every addressable CONFENGE
company decision, not only the expensive-enrichment hot set: eligible companies,
`TARGET_OUT_OF_SCOPE`, `TARGET_INSUFFICIENT_EVIDENCE`, DNC and valid-CNPJ
exclusions all remain present.

Every lead requires `target_fit_class`, `target_fit_fresh`,
`target_fit_version`, `target_fit_computed_at`,
`target_fit_source_watermark`, `target_fit_evidence_ids`,
`target_fit_send_tier` and `email_send_ready`. A CNPJ omitted from the supplied
snapshot is emitted as `TARGET_FIT_MISSING` with
`target_fit_tombstone=true` and `email_send_ready=false`; an older CONFIRMED
authorization can therefore never survive by omission.

The production pipeline reads the canonical CDC watermark from the target-fit
control plane, uses it for freshness evaluation, and records it as
`manifest.source.datalake_watermark`. An explicit non-tombstone decision with
an empty version, computation timestamp, or source watermark aborts the export.

Chunks are ordered ascending by source watermark, computation timestamp and
CNPJ. Import is authorized only when
`manifest.authoritative_target_fit.coverage_complete=true`,
`ordering.watermarks_monotonic=true` and
`omission_preserves_authorization=false`. A smoke limit or undeclared universe
produces a visibly partial manifest.

## Serve / import chunks

### File import (Warmbly side)

After checking the authoritative manifest gates, point Warmbly import at a chunk file or directory of chunks (see Warmbly
docs / PR #4 import API). Each `chunk_*.json` is a self-contained feed with
`schema_version`, `source`, `pagination`, and `leads`.

### Local HTTP static serve (optional)

```bash
python3 -m http.server 8765 --directory /tmp/confenge-outreach-out
# Warmbly can fetch: http://127.0.0.1:8765/chunk_0000.json
# Follow pagination.has_more / next_cursor via manifest.chunks
```

## Outcome receptor (extra-cli)

Warmbly posts `confenge.outcome.v1` with:

```
X-Warmbly-Signature: t=<unix>,v1=<hex(hmac_sha256(secret, "<unix>." + body))>
```

### Configure secret

```bash
export CONFENGE_OUTCOME_WEBHOOK_SECRET='use-a-long-random-secret'
# On Warmbly: CONFENGE_OUTCOME_WEBHOOK_URL + CONFENGE_OUTCOME_WEBHOOK_SECRET
```

### Run local receptor

```bash
# In-memory store (dev / CI without Postgres):
python3 -m scripts.warmbly_bridge serve-outcomes \
  --host 127.0.0.1 --port 8787 \
  --secret "$CONFENGE_OUTCOME_WEBHOOK_SECRET" \
  --memory-store

# Decision & Outcome Memory (Postgres):
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.warmbly_bridge serve-outcomes \
  --host 127.0.0.1 --port 8787 \
  --secret "$CONFENGE_OUTCOME_WEBHOOK_SECRET" \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --client-id confenge
```

Default path: `POST /webhooks/warmbly/outcome`  
Warmbly env: `CONFENGE_OUTCOME_WEBHOOK_URL=http://127.0.0.1:8787/webhooks/warmbly/outcome`

### Sign / verify a fixture body

```bash
python3 -m scripts.warmbly_bridge verify-outcome \
  --body scripts/warmbly_bridge/fixtures/outcome_contacted.json \
  --secret "$CONFENGE_OUTCOME_WEBHOOK_SECRET" \
  --sign
# → prints X-Warmbly-Signature value

python3 -m scripts.warmbly_bridge verify-outcome \
  --body scripts/warmbly_bridge/fixtures/outcome_contacted.json \
  --secret "$CONFENGE_OUTCOME_WEBHOOK_SECRET" \
  --signature 't=...,v1=...'
```

## Roundtrip check

1. Export fixtures → inspect `manifest.json` + one chunk (`schema_version`, leads).
2. Start `serve-outcomes` with a known secret and `--memory-store`.
3. Sign fixture outcome and POST:

```bash
BODY=scripts/warmbly_bridge/fixtures/outcome_contacted.json
SIG=$(python3 -m scripts.warmbly_bridge verify-outcome --body "$BODY" --secret "$CONFENGE_OUTCOME_WEBHOOK_SECRET" --sign | python3 -c "import sys,json; print(json.load(sys.stdin)['signature'])")
curl -sS -X POST "http://127.0.0.1:8787/webhooks/warmbly/outcome" \
  -H "Content-Type: application/json" \
  -H "X-Warmbly-Signature: $SIG" \
  --data-binary @"$BODY"
# Expect HTTP 200 and {"ok": true, "created": true, ...}
# Replay same request → 200, created=false (idempotent)
```

4. With Postgres DM: use `--dsn` and confirm row via  
   `python3 -m scripts.decision_memory` list outcomes for `client_id=confenge`.

## Secret rotation

1. Generate a new secret (`openssl rand -hex 32`).
2. Deploy **extra-cli** receptor with the new secret (or dual-accept window if you extend the receptor).
3. Update Warmbly `CONFENGE_OUTCOME_WEBHOOK_SECRET` to the new value.
4. Drain Warmbly outcome outbox / retry failed deliveries.
5. Revoke the old secret from extra-cli config.
6. Never commit secrets; rotate after any leak or staff change.

## Event mapping (honest)

Warmbly wire types (`CONTACTED`, `REPLIED`, `MEETING`, `PROPOSAL`, `WON`,
`LOST`, `DO_NOT_CONTACT`/`DNC`, `BOUNCED`/`BOUNCE`, `SENT`, `LEAD_REVIEWED`/`REVIEWED`)
are stored in Decision Memory `dm_outcome_events` with:

- `structured_facts.warmbly_event_type` + channel + suggested commercial state
- `OutcomeType` best-effort mapping (procurement enum is **not** isomorphic)
- **WON** only when `metadata.human_confirmed=true` (or equivalent human signal)

`DO_NOT_CONTACT` and other human-dominant commercial states remain dominant;
this bridge never invents contacts, consent, or facts.

## Tests

```bash
python3 -m pytest tests/warmbly_bridge/ -q --tb=short --no-cov
```

## Composition with CONFENGE motor

After parallel fronts land (universe ranking, account-intelligence,
contact-resolution), point `--universe` / `--account-intelligence` / `--contacts`
at their versioned JSONL outputs. Field contracts are the minimal keys in
`scripts/warmbly_bridge/fixtures/`; richer fields compose without rewriting this
bridge.
