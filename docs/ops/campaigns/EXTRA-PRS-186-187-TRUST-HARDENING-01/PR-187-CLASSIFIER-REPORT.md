# PR #187 Classifier Report

## Gate design
- Only `aec_confirmed` feeds indexable market/price/competition aggregates (pre-existing, preserved).
- Gold set fixture: 83 stratified cases in `tests/pseo/fixtures/gold_classification.json`.

## Fixture classification counts (sample export)
| Label / status | n |
|----------------|---|
| non_aec | 20 |
| insufficient_context | 16 |
| ambiguous | 4 |
| bid_status_aberta | 8 |
| bid_status_encerrada | 51 |
| bid_status_historico | 1 |

## Residual honesty
- Precision thresholds (0.97 global / 0.95 per segment) are enforced by the gold tests in `test_classifier.py`; this campaign did not re-label production gold.
- No claim of zero false positives in live national data.
