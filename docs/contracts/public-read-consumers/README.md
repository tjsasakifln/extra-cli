# public-read-consumers

Named SELECT-only read models for three web-cfg jobs. There is no generic
public-intelligence API and no second truth plane.

## Consumers

| consumer_id | schema | job |
|---|---|---|
| `web-cfg/contract-analysis` | `public-read-contract-analysis/1.0` | web-cfg#83 / PR #85 |
| `web-cfg/market-answer/valor-tipico-contratos-pavimentacao` | `public-read-market-answer-pavimentacao/1.0` | web-cfg#84 |
| `web-cfg/b2g-xray` | `public-read-b2g-xray/1.0` | web-cfg#84 / #88 |

Each record in `registry.json` declares grain, keys, source tables, allowed
fields, value semantics, evidence refs, as_of/freshness, coverage,
UNKNOWN/suppression, max rows/pagination/cache, fail-closed reason codes and
invalidation keys.

## CLI

```bash
python3 -m scripts.public_read_consumers list
python3 -m scripts.public_read_consumers validate
python3 -m scripts.public_read_consumers validate --consumer contract-analysis
python3 -m scripts.public_read_consumers export --consumer contract-analysis --fixture PATH --out DIR
python3 -m scripts.public_read_consumers export --consumer market-answer-pavimentacao --fixture PATH --out DIR
python3 -m scripts.public_read_consumers export --consumer b2g-xray --fixture PATH --out DIR
python3 -m scripts.public_read_consumers compare --left DIR --right DIR
python3 -m scripts.public_read_consumers verify --path DIR
```

`--fixture` never labels the export as live (`producer_status=CONTRACT_FIXTURE`,
`official_live=false`). `--live` is refused unless official producers exist and
the gate passes.

## Compatibility

Contract-analysis exports the layout already consumed by web-cfg PR #85:
`schema == public-read-contract-analysis/1.0`, `manifest.json` +
`analyses/<id>.json`, `data_state` / `publication_readiness` in
`DATA_READY|DATA_HOLD|DATA_REJECT`, `catalog_mode=fixture` on the fixture path,
`claimed_live=false`. The adapter does not rewrite that contract.

## Producers in parallel

#414, #415 and #302 are consumed as labeled documents
(`producer_status=CONTRACT_FIXTURE`). See `INTEGRATION_NOTES.md` for the
field-by-field swap after those PRs merge. Do not close extra-cli#400 on
fixture proof alone.
