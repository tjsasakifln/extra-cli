# Reconciliation report — `reconcile-20260717T023428Z-3b096d2b41`

- **mode**: `smoke`
- **started_at**: 2026-07-17T02:34:28.289915+00:00
- **completed_at**: 2026-07-17T02:34:28.892762+00:00

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

- `compras_sc_id_crosswalk` (score=0.92): 30

## Claims allowed

- ✅ initial_deterministic_reconciliation_smoke_or_sample
- ✅ match_rows_reversible_file_backed
- ✅ rules_used=compras_sc_id_crosswalk
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

- `2662355a5431a505bce41482` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60847 ↔ pncp:sc-60847
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60847') left=compras_sc:sc-60847 right=pncp:sc-60847
- `49286a512c0b85208e83aa5d` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60848 ↔ pncp:sc-60848
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60848') left=compras_sc:sc-60848 right=pncp:sc-60848
- `9b80010333e30bb11e6bddd5` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60849 ↔ pncp:sc-60849
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60849') left=compras_sc:sc-60849 right=pncp:sc-60849
- `3587b6e3914a7efc5f579ee0` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60850 ↔ pncp:sc-60850
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60850') left=compras_sc:sc-60850 right=pncp:sc-60850
- `b634b34b3254bda812b3bac7` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60851 ↔ pncp:sc-60851
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60851') left=compras_sc:sc-60851 right=pncp:sc-60851
- `8292ee1137ad722261cf5f83` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60852 ↔ pncp:sc-60852
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60852') left=compras_sc:sc-60852 right=pncp:sc-60852
- `5a664a47927b600a29540e00` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60853 ↔ pncp:sc-60853
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60853') left=compras_sc:sc-60853 right=pncp:sc-60853
- `a8ff2040b44bddec1899e509` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60854 ↔ pncp:sc-60854
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60854') left=compras_sc:sc-60854 right=pncp:sc-60854
- `239d7983d04db28c6f531a6c` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60855 ↔ pncp:sc-60855
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60855') left=compras_sc:sc-60855 right=pncp:sc-60855
- `fc7d2e8986c139e631028856` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-60856 ↔ pncp:sc-60856
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-60856') left=compras_sc:sc-60856 right=pncp:sc-60856
- `6c814b9191858826f9ac1f32` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-41624 ↔ pncp:sc-41624
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-41624') left=compras_sc:sc-41624 right=pncp:sc-41624
- `36af1ee149a9955d3b13a28e` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-57612 ↔ pncp:sc-57612
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-57612') left=compras_sc:sc-57612 right=pncp:sc-57612
- `e22987bf499b0e5f4927432b` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58075 ↔ pncp:sc-58075
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58075') left=compras_sc:sc-58075 right=pncp:sc-58075
- `00db4107fb8b2a9067e1641d` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58109 ↔ pncp:sc-58109
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58109') left=compras_sc:sc-58109 right=pncp:sc-58109
- `55ec6512e16e6d48d7588303` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58110 ↔ pncp:sc-58110
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58110') left=compras_sc:sc-58110 right=pncp:sc-58110
- `abace3a378d7aa48c089a6e7` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58111 ↔ pncp:sc-58111
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58111') left=compras_sc:sc-58111 right=pncp:sc-58111
- `1e82efdc6123bf3e2645613e` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58112 ↔ pncp:sc-58112
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58112') left=compras_sc:sc-58112 right=pncp:sc-58112
- `cf7711a0dc27678dff930688` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58115 ↔ pncp:sc-58115
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58115') left=compras_sc:sc-58115 right=pncp:sc-58115
- `1bcdf03870035ac766d932d5` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58117 ↔ pncp:sc-58117
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58117') left=compras_sc:sc-58117 right=pncp:sc-58117
- `7fe94a99d8499fed73a4c078` rule=`compras_sc_id_crosswalk` score=0.92 compras_sc:sc-58118 ↔ pncp:sc-58118
  - rule=compras_sc_id_crosswalk score=0.92 keys=(compras_sc_id='sc-58118') left=compras_sc:sc-58118 right=pncp:sc-58118
