# CONFENGE-EXTRA-LIVE-COMPARABLES-01

Live producer slice for extra-cli #415. Consumer: web-cfg #83|#84 after this release. No publication. No index.

## Question

How does the nominal integral value of PNCP `14862788000150-2-000069/2026` sit among really comparable paving contracts?

Secondary BRL/m² was not emitted: peers do not have documented comparable area/unit/scope.

## Live result

| Field | Value |
|---|---|
| `origin/main` | `939f0a1b00cc9f12869e2624c647203ea87b1e41` |
| producer commit | `db73775c6340925d34b48cfe8128dd94e5fd8d69` |
| target | `14862788000150-2-000069/2026` |
| source | `pncp_contrato_api` |
| official_live | true |
| catalog_mode | `live_candidate` |
| DSN | unavailable |
| window | 2026-07-01 .. 2026-08-19 |
| `peer_group_id` | `pg-1ee8488f3bfb0291` |
| total_found / eligible / used | 1 / 1 / 0 |
| state | `HOLD_FOR_DATA` |
| metrics | none (gate did not pass) |
| reason codes | `live_columns_unavailable`, `fields_unavailable`, `unit_unknown` |
| content_hash | `5b05592fc83a2c2216800beb7d2c25f616dca4fcf6ef0c0c319a8f481c53044d` |
| two isolated replays | identical content_hash |
| geography as written | UF PI, listing município Teresina (objeto names São Gonçalo do Piauí; not inferred) |
| publication / index | false / false |
| backfill | false |

PNCP consulta pages in the window timed out after bounded retries. The focal contract JSON was retrieved. That is unavailability of the peer universe, not world absence of paving contracts.

Seed AEC listing sha256 `89a3ba4c…` is the consulta listing body. This canary hashed the contract API URL `…/orgaos/14862788000150/contratos/2026/69` (`f14acac4…`). Different locator, different bytes.

## Why not COMPARABLE

Versioned `MIN_USABLE_N_COMPARABLE=5` was not lowered. Official locators still lack `unidade`, `quantidade`, `regime`, `modalidade`. Unknown is not coerced to `BRL_TOTAL` or zero. n usable = 0.

## Consumer

Handoff: `exports/authority-handoff/contract-comparables/1.0/paving-nominal-14862788000150-2-000069-2026/`

`READY.json` means the producer finished a fail-closed live envelope. It does not authorize a page.

Replay:

```
python3 -m scripts.contract_comparables live-paving-handoff --focal 14862788000150-2-000069/2026 --as-of 2026-08-19 --start-date 2026-07-01 --end-date 2026-08-19 --limit 200 --metric valor_integral_nominal
```

## Residual on #415

Keep #415 open until a live `COMPARABLE` peer group exists with official semantic fields and usable n ≥ 5. Do not close #400, #414 or #302.
