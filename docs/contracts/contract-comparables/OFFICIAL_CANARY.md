# Official paving canary — EXTRA-010 / #415

Entry point: `python3 -m scripts.contract_comparables official-canary`

This command is the official-sample residual on top of inbound PR #418. It
reuses `scripts.contract_comparables` and does not open a second producer.

## What counts as success

Exactly one of:

| Status | When |
|--------|------|
| `COMPARABLE` | Official paving rows, proven typology/regime/unit/semantic/coverage, usable n |
| `HOLD_FOR_DATA` | Official rows exist but semantic columns, quantity/unit or coverage are missing |
| `NOT_COMPARABLE` | Proven incompatibility (typology/regime/geo/period/unit) or metric outside the whitelist |
| `BLOCKED` | DSN/host/table/dataset official ausente; pré-requisito e próximo comando nominais |

`catalog_mode=official_live` is forbidden until `unidade`, `quantidade`,
`regime`, `modalidade` and `valor_semantic` exist **and** coverage is proven.
Keyword typology is the documented method; it is not those columns.

Fixture `COMPARABLE` from `build --case comparable_clear` is not official proof.

## Metric whitelist

Only `valor_integral_nominal` (aliases `valor`, `ticket`). Median / P25 / P75
and robust distances are emitted only after the peer-group gate passes.

`custo/km`, `cost_per_km`, `custo/m2`, `unit_price` → `HOLD_FOR_DATA` with
`physical_unit_price_not_verified`. `UNKNOWN` never becomes zero.

## Official stratum

`pncp_supplier_contracts` is national. The canary fetches paving-like rows
and then keeps **only the focal UF** before `build_peer_group`. A mixed-UF
dump with missing semantic columns is `HOLD_FOR_DATA`
(`live_columns_unavailable`), not `NOT_COMPARABLE` /
`geography_not_comparable`. Geography remains a hard refusal only after
semantics exist and the focal UF stratum is still incompatible.

## Replay

```bash
python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01
python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01
# content_hash must match
```

With a snapshot:

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01 --limit 200
```

## Dependencies still open

- EXTRA-003: no local branch
- EXTRA-004 (`feat/extra-004-official-national-catalog`): not in `origin/main`
- EXTRA-008 (`feat/extra-008-live-consumers`): not in `origin/main`
- Consumer web-cfg#84 / extra-cli#400: reads the document; this slice is producer-only
