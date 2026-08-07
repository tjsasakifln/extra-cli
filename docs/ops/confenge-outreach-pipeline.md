# CONFENGE outreach pipeline

Canonical path (no manual JSON handoff):

```text
universe → diverse sample → account intelligence → contact resolution → confenge.outreach.v1
```

## Command

```bash
python -m scripts.confenge_outreach_pipeline run \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --out output/confenge_outreach \
  --as-of 2026-08-07 \
  --limit-downstream 200
```

### Flags

| Flag | Role |
|------|------|
| `--dsn` | National datalake (or `LOCAL_DATALAKE_DSN`) |
| `--out` | Output root |
| `--as-of` | Reference date |
| `--limit-downstream` | Caps **only** intelligence / contacts / feed |
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
