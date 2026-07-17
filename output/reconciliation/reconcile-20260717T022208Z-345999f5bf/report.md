# Reconciliation report — `reconcile-20260717T022208Z-345999f5bf`

- **mode**: `smoke`
- **started_at**: 2026-07-17T02:22:08.328560+00:00
- **completed_at**: 2026-07-17T02:22:08.983602+00:00

## Counts

| Metric | Value |
|--------|------:|
| reconciled (match pairs) | 30 |
| PNCP-only | 380 |
| DOE-only | 200 |
| DOM-only | 200 |
| Compras SC-only | 0 |
| status divergences | 0 |
| date divergences | 0 |
| value divergences | 0 |
| missing documents | 30 |
| needs review | 0 |
| DB matches written | 0 |

## Sources loaded

- **pncp**: 410
- **doe**: 200
- **dom**: 200
- **compras_sc**: 30

## Rules applied

- `pncp_number_exact` (score=1.0): 30

## Claims allowed

- ✅ initial_deterministic_reconciliation_smoke_or_sample
- ✅ match_rows_reversible_file_backed
- ✅ rules_used=pncp_number_exact
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

- `bfed26357e65d2648aef8e3d` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60847 ↔ pncp:sc-60847
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60847') left=compras_sc:sc-60847 right=pncp:sc-60847
- `a4bfe6dede81e18cc57c055d` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60848 ↔ pncp:sc-60848
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60848') left=compras_sc:sc-60848 right=pncp:sc-60848
- `940e0932062bb4391af43e1c` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60849 ↔ pncp:sc-60849
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60849') left=compras_sc:sc-60849 right=pncp:sc-60849
- `d737874b40777d6700ee96f0` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60850 ↔ pncp:sc-60850
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60850') left=compras_sc:sc-60850 right=pncp:sc-60850
- `c387a1964ee23f6727f9fbe7` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60851 ↔ pncp:sc-60851
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60851') left=compras_sc:sc-60851 right=pncp:sc-60851
- `c89dd824d7811e51a1cd057e` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60852 ↔ pncp:sc-60852
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60852') left=compras_sc:sc-60852 right=pncp:sc-60852
- `1cb4cdd33ba14f0ef6a86fcb` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60853 ↔ pncp:sc-60853
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60853') left=compras_sc:sc-60853 right=pncp:sc-60853
- `391597a4ade9f3a384306af3` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60854 ↔ pncp:sc-60854
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60854') left=compras_sc:sc-60854 right=pncp:sc-60854
- `012406e27efc0ad2c3f937df` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60855 ↔ pncp:sc-60855
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60855') left=compras_sc:sc-60855 right=pncp:sc-60855
- `ea98b09ba2a44d2b6a5e9f72` rule=`pncp_number_exact` score=1.0 compras_sc:sc-60856 ↔ pncp:sc-60856
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-60856') left=compras_sc:sc-60856 right=pncp:sc-60856
- `9bd6e510785334c5102264d2` rule=`pncp_number_exact` score=1.0 compras_sc:sc-41624 ↔ pncp:sc-41624
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-41624') left=compras_sc:sc-41624 right=pncp:sc-41624
- `70a4352bada3f12f32a807c2` rule=`pncp_number_exact` score=1.0 compras_sc:sc-57612 ↔ pncp:sc-57612
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-57612') left=compras_sc:sc-57612 right=pncp:sc-57612
- `a5690cc9bea59c8ad6f26755` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58075 ↔ pncp:sc-58075
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58075') left=compras_sc:sc-58075 right=pncp:sc-58075
- `1407610bcf87a9a85990285c` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58109 ↔ pncp:sc-58109
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58109') left=compras_sc:sc-58109 right=pncp:sc-58109
- `b43e8016ef9b005ee46cb7bb` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58110 ↔ pncp:sc-58110
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58110') left=compras_sc:sc-58110 right=pncp:sc-58110
- `3b6b8627b2a980f93f62ad73` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58111 ↔ pncp:sc-58111
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58111') left=compras_sc:sc-58111 right=pncp:sc-58111
- `1e12373afc2fe70d9bb6d1ab` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58112 ↔ pncp:sc-58112
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58112') left=compras_sc:sc-58112 right=pncp:sc-58112
- `61cf8b84d0803dbab5856ef1` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58115 ↔ pncp:sc-58115
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58115') left=compras_sc:sc-58115 right=pncp:sc-58115
- `458f22720fdaaba14ca9b6fc` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58117 ↔ pncp:sc-58117
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58117') left=compras_sc:sc-58117 right=pncp:sc-58117
- `0250a4090d37b364279b03cd` rule=`pncp_number_exact` score=1.0 compras_sc:sc-58118 ↔ pncp:sc-58118
  - rule=pncp_number_exact score=1.0 keys=(pncp_number='sc-58118') left=compras_sc:sc-58118 right=pncp:sc-58118
