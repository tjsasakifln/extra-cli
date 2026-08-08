# CONFENGE final integration — extra-cli FINAL-REPORT

Generated: 2026-08-08T01:39:56.016776+00:00
SHA: `7cf9593d68afad00006f578cc7324aee506cebe2`
Branch: `campaign/confenge-final-integration-01`
PR: #206

## Verdict (extra-cli scope)

| Item | Status |
|------|--------|
| full national universe | PASS (`full_scale=true`, eligibles=48748) |
| reconciliation | PASS |
| diverse downstream sample (200) | PASS |
| account intelligence | PASS |
| contact resolution (network) | PASS for honesty; phones=95 / 200; emails verified=0 |
| confenge.outreach.v1 feed | PASS run_id=None |
| fingerprint source_hash | PASS (id column mapping fixed) |
| contact cache network isolation | PASS (cache key includes allow_network) |

## Absolute rules honored

- No pattern-guess enrollment
- Public phone ≠ WhatsApp opt-in
- No final marketing copy in extra-cli
- No send to real leads

## Commands

```bash
export LOCAL_DATALAKE_DSN='postgresql://postgres:***@127.0.0.1:54399/postgres'
python3 -m scripts.confenge_outreach_pipeline run \
  --dsn "$LOCAL_DATALAKE_DSN" --out artifacts/confenge/full-national-2026-08-07 \
  --as-of 2026-08-07 --limit-downstream 200 --allow-network
```

## Artifacts

- `artifacts/confenge/full-national-run.json`
- `artifacts/confenge/full-national-manifest.json`
- `artifacts/confenge/downstream-real-sample.json`
- `artifacts/confenge/contact-resolution-metrics.json`
- `artifacts/confenge/confenge-outreach-feed-manifest.json`
- `artifacts/confenge/full-national-2026-08-07/` (full run tree)
