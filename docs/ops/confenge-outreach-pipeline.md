# CONFENGE outreach pipeline

Canonical **production** path (no manual JSON handoff):

```text
universe → activation planner → hot set → account intelligence
  → contact resolution → confenge.outreach.v1
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
  --use-activation-planner

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
| `--max-workers` | Concurrency for expensive stages |
| `--max-rows` | **Diagnostic sampling** of universe source; never claim full-scale when set |
| `--csv` | Offline fixture path |
| `--skip-contacts` | Empty contacts (offline speed) |

`--limit-downstream` does **not** limit universe discovery.

## Outputs

```text
01_universe/          confenge-universe-v1.jsonl + manifest
02_downstream_sample/ diverse commercial sample
03_account_intelligence/
04_contact_resolution/
05_bridge_inputs/     joined shapes for warmbly_bridge
06_warmbly_feed/      chunked confenge.outreach.v1
reports/pipeline-manifest.json
```

## Real datalake columns

`pncp_supplier_contracts` physical names (`ni_fornecedor`, `valor_global`, `id`, …)
are mapped to logical fields in `scripts/confenge_universe/source.py`.

## Full-scale honesty

Only runs with DSN and **without** `--max-rows` may set `full_scale=true`.
Sampled runs must not be presented as national full-scale proof.
