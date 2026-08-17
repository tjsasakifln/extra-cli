# Evidence — extra-cli

Classes are not collapsed.

## BACKFILL_COMPLETO — LIVE_PROVEN + CODE_PROVEN

- Command (twice): `python3 -m scripts.ops.audit_pncp_national_backfill --checkpoint hc_closure_3y.json --lake lake-live.json`
- Verdict both runs: `BACKFILL_COMPLETO`
- Window matrix hash both runs: `a8e43af599f4d5511c1dae030990f5e5c99031c7dfa9b193f2323efba0b9c7bd`
- Checkpoint sha256: `17ff50a4d47dc6d5e17541940f95325efbd76c80a0c1bd07c481d240e9312bf8`
- Lake COUNT(*) via SSH+psql and via tunneled SELECT: `4573257`

## Incremental — LIVE_PROVEN, not INCREMENTAL_HEALTHY

- `pncp-contracts.timer` last trigger 2026-08-17 06:03-03, next Wed 19 06:00-03
- Journal: 90 pages, `ins_total=261`, then `status=failed` `source_population_drift:totalRegistros 44515 -> 44517`
- `max(ingested_at)` / `max(last_seen_at)` = 2026-08-17T11:29:37+02

## Market Answer SC — CODE_PROVEN on official lake SELECT

- Entry: shipped `PAVING_ILIKE` + `_percentile` + `project_market_answer` + `export_consumer(..., live=True)`
- Two runs: `n=5038`, median `218284.5`, P25 `19969.495`, P75 `708950.0`, `official_live=true`, `answer_state=DATA_READY`, geography `SC`
- Folded payload hash (timestamps dropped): `9b69e30cb9e696a6c268526b3646f2d1588519849c5024aa46e6ba89ec06c0b6`
- Content hashes differ only by `generated_at` / freshness
- Artifacts: `exports/market-answer-sc/{payload,manifest}.json`

## Comparables — CODE_PROVEN live probe, official_live withheld

- `python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01 --metric valor_integral_nominal`
- Run 2: `catalog_mode=live_candidate`, `status=NOT_COMPARABLE`, missing columns `unidade,quantidade,regime,modalidade,valor_semantic`
- `active_row_count=4573257`
- File: `exports/official-canary-415.json`

## X-Ray — LIVE_PROVEN empty surface

- `public_read_v1` schema exists; `current_snapshot`, `contracts`, `entities` COUNT=0
