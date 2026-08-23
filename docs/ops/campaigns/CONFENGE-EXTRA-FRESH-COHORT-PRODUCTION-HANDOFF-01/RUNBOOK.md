# RUNBOOK — bounded controlled-email cohort

How to produce a fresh cohort input and hand it to Warmbly. Every step below is
shipped code or a canonical CLI. Nothing here sends mail: extra-cli is the
intelligence/truth plane, Warmbly owns delivery.

## Invariants

- Zero SMTP. Zero mail send from extra-cli.
- `auto_send` stays false. Warmbly keeps `CONFENGE_REQUIRE_HUMAN_APPROVAL=true`.
- `PROBABILISTIC_OR_RISKY` is outside the default pilot.
- Exactly one `preferred_initial` route per account.
- The first real cohort is capped at `10/day`; this runbook must not be used to
  raise that limit.
- A feed is fresh only when it embeds a current
  `PNCP_CONTRACT_FRESHNESS/1.0` attestation with `status=FRESH` and an
  unexpired `expires_at`. Missing, PARTIAL, STALE or DEGRADED evidence blocks
  export and cohort cutting.
- The feed holds operational PII and never enters Git. Only schema, code,
  hashes, counts, route-class aggregates and host-level evidence do.

## 1. Bind the executed code

The producer must run at a SHA that is on `main`.

```bash
ssh ec-prod
cd /opt/extra-consultoria
git fetch origin main
git checkout --detach "$TARGET_SHA"
git rev-parse HEAD          # executed SHA, recorded in the manifest
```

## 2. Run the pipeline

`--use-activation-planner` selects the ICP: the canonical PNCP construction
universe, ranked by activation state. Capacity is the size of the hot set the
cascade will actually investigate — raise it when the eligible yield falls
short, never pad the cohort.

```bash
set -a; source /opt/extra-consultoria/.env; set +a
export PYTHONPATH=/opt/extra-consultoria
.venv/bin/python -m scripts.confenge_outreach_pipeline run \
  --out "$OUT_ROOT" \
  --use-activation-planner \
  --activation-capacity 500 \
  --allow-network \
  --enable-web-search \
  --max-workers 4 \
  --no-resume
```

The discovery cascade walks: official site → public domain evidence → role and
department mailboxes → generic company → associated public freemail → person
discovery → passive DNS/MX. No SMTP probe at any step.

## 3. Cut the bounded cohort

```bash
.venv/bin/python -m scripts.ops.build_controlled_email_cohort \
  --feed-dir "$OUT_ROOT/06_warmbly_feed" \
  --private-root /var/lib/extra-consultoria/private/outreach/cohorts \
  --limit 10
```

The producer re-derives eligibility from each contact's own provenance instead
of trusting the exported stamp, so a feed built by an older classifier cannot
smuggle a route the current policy rejects. It then writes, mode `0600`:

| File | Content |
| --- | --- |
| `confenge.outreach.v1.json` | the cohort feed — holds PII |
| `confenge.outreach.v1.json.sha256` | hash of those exact bytes |
| `manifest.redacted.json` | funnel, distribution, stratified sample, no PII |

Exit status is non-zero when the cohort is empty. An empty cohort is a real
result, not a failure to work around.

## 4. Review the sample before handing off

Read `manifest.redacted.json`. For each sampled route confirm the mailbox
domain and the evidence host are consistent with the company, and that the
source URL is a company surface rather than a tracking or unsubscribe link. If
one route class or one source shows a systematic error, block that class and
re-cut — do not hand off a cohort that is technically valid and commercially
wrong. Do not claim a precision figure the sample cannot support.

## 5. Hand off to Warmbly

Publish onto the canonical transport, then let Warmbly import and derive its
own hashes. Never write Warmbly tables directly, never copy a hash by hand.

Four things about the live runtime that the command shapes depend on:

- `confenge import --feed` takes a **URL** and enforces the transport gate
  (https only, host allowlist, no redirects, size cap, `schema_version` exact
  match, `generated_at` not more than five minutes in the future).
- `confenge cohort prepare --feed` takes a **local file path inside the
  container**. It does not fetch URLs and it does not re-validate the schema.
- `cohort prepare` needs `--feed` *and* `--org-id` together. The feed supplies
  the run identity, the org supplies the real account and candidate ids that a
  later dispatch would need. Either flag alone yields a manifest that cannot
  both pass review and dispatch, and the scoped mode fails closed unless
  `import` already loaded that `source.run_id`.
- The feed must carry a non-empty `source.run_id`, or the scoped freeze blocks.

```bash
NAME=controlled-email-cohort-fresh
BE=warmbly-confenge-backend-1
# Read the operator org from the runtime rather than pinning an id that drifts.
ORG=$(docker exec $BE printenv CONFENGE_OPERATOR_ORG_ID)

cp "$FEED" /opt/confenge-plane/feed-www/$NAME.json

# Validate over the canonical transport first. A dry run still records one
# outreach_import_runs row; it touches no account, candidate or outcome.
docker exec $BE /app/confenge import --feed https://confenge-feed:8443/$NAME.json --org-id $ORG --dry-run
docker exec $BE /app/confenge import --feed https://confenge-feed:8443/$NAME.json --org-id $ORG

# Stage the same bytes as a file, then freeze.
docker exec $BE wget -q -O /data/confenge-ops/$NAME.json https://confenge-feed:8443/$NAME.json
docker exec $BE /app/confenge cohort prepare \
  --feed /data/confenge-ops/$NAME.json --org-id $ORG \
  --out /data/confenge-ops/$NAME-frozen.json --limit 10 --max-daily 10 --ttl 24h
docker exec $BE /app/confenge cohort preview --manifest /data/confenge-ops/$NAME-frozen.json
```

`cohort prepare` derives `cohort_hash` and `recipient_set_hash` on the Warmbly
side and writes them into the frozen snapshot. Read them from that file — never
transcribe a hash by hand. Check `reconciled=true` in the preview. Remove the
transport copy once the import reports `status=completed`; the frozen manifest
holds real mailboxes and stays under `/data/confenge-ops`.

**Stop there.** `cohort authorize`, `cohort review` and `cohort dispatch` arm
and then perform sending, and `resume-sending` deletes the kill switch. None of
them belong in a producer handoff. Everything up to and including
`cohort preview` creates no touchpoint, no authorization grant and no message.

Two contract details worth knowing before composing the feed: a freemail
mailbox is only classified `PUBLIC_COMPANY_FREEMAIL` when the contact carries
`mailbox_company_evidence: "OBSERVED"`, and contact-level `reason_codes` are
dropped on import — activation reason codes belong on the lead.

## 6. Record the evidence

Update `manifest.json` in this directory with the merged SHA, the executed SHA,
the run id, the private feed path, the feed hash, the member count, the
route-class distribution, the funnel and the import result. Counts and hashes
only — the mailboxes stay on the host.
