# CONFENGE outreach pipeline

Canonical **production** path (no manual JSON handoff):

```text
full supplier decision universe → activation planner → hot set
  → account intelligence/contact resolution for the hot set
  → authoritative confenge.outreach.v1 for the full decision universe
```

Smoke / diagnostic path (not a commercial shortlist strategy):

```text
universe → diverse sample (--force-sample-mode) → expensive stages
```

See also: [confenge-activation-planner.md](./confenge-activation-planner.md).

## Command

```bash
# Production: capacity-aware activation hot set
python -m scripts.confenge_outreach_pipeline run \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --out output/confenge_outreach \
  --as-of 2026-08-07 \
  --use-activation-planner \
  --durable-contacts output/contact-discovery/contacts.jsonl

# Smoke only
python -m scripts.confenge_outreach_pipeline run \
  --csv tests/fixtures/confenge_universe/contracts_sample.csv \
  --out /tmp/confenge_smoke \
  --force-sample-mode \
  --limit-downstream 20 \
  --skip-contacts
```

### Flags

| Flag | Role |
|------|------|
| `--dsn` | National datalake (or `LOCAL_DATALAKE_DSN`) |
| `--out` | Output root |
| `--as-of` | Reference date |
| `--use-activation-planner` / `--no-use-activation-planner` | Production hot set from planner (default on) |
| `--force-sample-mode` | Smoke: diverse sample instead of activation |
| `--activation-capacity` | Override hot-set size (policy capacity by default) |
| `--limit-downstream` | Smoke sample size only; **not** production commercial strategy |
| `--feed-limit` | Rejected: truncating an authoritative decision snapshot is unsafe |
| `--max-workers` | Concurrency for expensive stages |
| `--max-rows` | **Diagnostic sampling** of universe source; never claim full-scale when set |
| `--csv` | Offline fixture path |
| `--skip-contacts` | Empty contacts (offline speed) |
| `--durable-contacts` | Hash-verified derived projection from the durable waterfall; its sibling `contact-projection-report.json` is mandatory for live publication |

`--limit-downstream` does **not** limit universe discovery or feed decisions.
It limits intelligence/contact work only in smoke/sample mode. In production,
the activation hot set bounds network contact work while deterministic
intelligence covers all authoritative `TARGET_CONFIRMED` accounts. The feed also
includes valid-CNPJ exclusions and DNC. Missing target-fit rows become explicit
`TARGET_FIT_MISSING` tombstones.

With `--dsn`, decisions come from the mode-aware published target-fit store
(shadow in SHADOW mode; current in ACTIVE/CANARY). The on-the-fly universe
classification is used only by offline fixture runs; a production store miss
does not fall back to an embedded CONFIRMED stamp.

The durable projection is the reachability view derived from extra-cli job
outputs, not a second authority. Its discovery policy and input evidence must
be uniform; mixed or incompatible policy versions fail closed. Same-run hot-set
contacts corroborate/extend it by canonical CNPJ and mailbox, after which the
bridge recalculates exactly one preferred initial route per account.

For a live DSN run, the projection report must prove complete terminal coverage
of the exact `TARGET_CONFIRMED` root membership. The exporter copies its
population, membership/projection hashes, terminal counts, route classes and
policy versions into the manifest. The atomic publisher recomputes membership
from all chunks and refuses partial, stale, mismatched or buyer-conflicted
authorization without replacing the last valid `current` release.

In production activation mode, the hot set remains the canary/capacity boundary
for network contact discovery, but it does not limit deterministic account
intelligence. Every account in the authoritative `TARGET_CONFIRMED` snapshot is
processed for service, public factual context and message spine before the
complete decision feed is exported. Smoke/sample mode remains bounded.

## Outputs

```text
01_universe/          included + excluded decision JSONLs + manifest
02_downstream_sample/ diverse commercial sample
03_account_intelligence/
04_contact_resolution/
05_bridge_inputs/     full universe + target-fit snapshot; durable+hot-set contacts
06_warmbly_feed/      temporally ordered authoritative confenge.outreach.v1
reports/pipeline-manifest.json
```

## Real datalake columns

`pncp_supplier_contracts` physical names (`ni_fornecedor`, `valor_global`, `id`, …)
are mapped to logical fields in `scripts/confenge_universe/source.py`.

## Full-scale honesty

Only runs with DSN and **without** `--max-rows` may set `full_scale=true`.
Sampled runs must not be presented as national full-scale proof.
