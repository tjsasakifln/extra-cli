# CONFENGE-EXTRA-LIVE-COMPARABLES-01

Live producer slice for extra-cli #415. Consumer: web-cfg #83|#84 after this release. No publication. No index.

## Question

How does the nominal integral value of PNCP `14862788000150-2-000069/2026` sit among really comparable paving contracts?

Secondary BRL/m² was not emitted: not every used peer documents comparable area/unit/scope.

## Live result

| Field | Value |
|---|---|
| `origin/main` | `939f0a1b00cc9f12869e2624c647203ea87b1e41` |
| target | `14862788000150-2-000069/2026` |
| source | `pncp_contrato_api+pncp_consulta_api` |
| official_live | true (bytes retrieved) |
| catalog_mode | `live_candidate` |
| DSN | absent (not configured; no local Postgres) |
| query | `/api/consulta/v1/contratos?cnpjOrgao=14862788000150` |
| window | 2026-07-01 .. 2026-08-19 |
| paving family | `paralelepipedo` |
| total_found / eligible / used | 16 / 13 / 12 |
| state | `COMPARABLE` |
| metric | `valor_integral_nominal` (median / P25 / P75) |
| unit | `BRL_TOTAL` via `official_total_value_field_is_instrument_total/1.0` |
| regime | UNKNOWN (unpublished on contract locator; not invented) |
| modalidade | FACT_OFFICIAL from linked compra (`Concorrência - Eletrônica`) |
| content_hash | `4f71782994e2821e363b7651ce24f6f1d673014cf8cd765adee431acfa437f73` |
| two isolated replays | identical content_hash |
| publication / index / national | false / false / false |

`MIN_USABLE_N_COMPARABLE=5` was not lowered.

## Residual that this cycle closed

The previous HOLD (`n found=1 / used=0`, `unit_unknown`, `live_columns_unavailable`) was not “no paving peers exist”. Root cause classes:

1. **Query:** swagger `/v1/contratos` accepts `cnpjOrgao`. Params `uf` and `cnpj` are ignored. Unfiltered national dump (289 007 rows) has ~0 paving on the first pages and used to time out at 15 s.
2. **DSN:** `LOCAL_DATALAKE_DSN` / `NATIONAL_INTEL_DSN` absent; 127.0.0.1:5432/5433 closed. Schema not probed.
3. **Semantic:** contract locator has `valorGlobal` (FACT) but no `unidade` / `regime` columns. `BRL_TOTAL` is a named derivation from the official total-value field, not km/m². Regime stays UNKNOWN and is not an inclusion key for this metric.
4. **Pares:** bounded org query returns 16 paving rows; family `paralelepipedo` keeps 13 (12 peers). CBUQ / TSD / recapeamento excluded with `paving_family_mismatch`.

## Why COMPARABLE without `catalog_mode=official_live`

Needed fields for `valor_integral_nominal` of the instrument are present on official locators (`valorGlobal`, objeto, UF, período). Execution regime is still unpublished, so the engine document stays `live_candidate`. Envelope `official_live=true` only means official PNCP bytes were retrieved.

## Consumer

Handoff: `exports/authority-handoff/contract-comparables/1.0/paving-nominal-14862788000150-2-000069-2026/`

`READY.json` means the producer finished a fail-closed live envelope. It does not authorize a page.

Replay:

```
python3 -m scripts.contract_comparables live-paving-handoff --focal 14862788000150-2-000069/2026 --as-of 2026-08-19 --start-date 2026-07-01 --end-date 2026-08-19 --limit 200 --metric valor_integral_nominal
```

## Residual on #415

Keep #415 open until a consumer page is authorized separately. Do not close #400, #414 or #302. Next consumer action: read `payload.json` / `state.json`. Do not INDEX or publish.
