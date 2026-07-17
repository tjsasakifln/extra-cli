# Reconciliation report — `reconcile-20260717T022055Z-49332bbb54`

- **mode**: `smoke`
- **started_at**: 2026-07-17T02:20:55.304780+00:00
- **completed_at**: 2026-07-17T02:20:55.870832+00:00

## Counts

| Metric | Value |
|--------|------:|
| reconciled (match pairs) | 0 |
| PNCP-only | 400 |
| DOE-only | 200 |
| DOM-only | 200 |
| Compras SC-only | 10 |
| status divergences | 0 |
| date divergences | 0 |
| value divergences | 0 |
| missing documents | 0 |
| needs review | 0 |
| DB matches written | 0 |

## Sources loaded

- **pncp**: 400
- **doe**: 200
- **dom**: 200
- **compras_sc**: 10

## Rules applied

- _(none)_

## Claims allowed

- ✅ initial_deterministic_reconciliation_smoke_or_sample
- ✅ match_rows_reversible_file_backed
- ✅ rules_used=none
- ✅ sources_attempted=pncp,doe,dom,compras_sc

## Claims forbidden

- 🚫 90_day_pilot_success
- 🚫 3_year_backfill_complete
- 🚫 full_coverage_claimed
- 🚫 fuzzy_text_similarity_linking
- 🚫 production_sync_complete
- 🚫 official_acts_table_fully_populated

## Notes

- Deterministic identifier matching only; no pure text-similarity linking.
- This run does NOT claim 90-day pilot success or 3-year backfill.
- Loaded 200 rows from official_acts DB.
- DOE loaded from files (none in official_acts).

## Sample matches (up to 20)

