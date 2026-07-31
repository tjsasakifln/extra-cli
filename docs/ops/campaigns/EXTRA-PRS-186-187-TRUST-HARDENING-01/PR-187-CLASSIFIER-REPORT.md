# PR #187 Classifier Report

## Gates (enforced in tests)

| Gate | Threshold | Test |
|------|-----------|------|
| Global precision `aec_confirmed` | **>= 0.97** | `test_gold_precision_gate` |
| Global false positives | **fp == 0** | `test_gold_precision_gate` |
| Per-segment precision | **>= 0.95** (segments with n>=3 and predicted positives) | `test_gold_precision_gate` |

`evaluate_classifier` returns `by_segment` metrics and `gates.segment_precision_threshold=0.95`.

## Gold set
- `tests/pseo/fixtures/gold_classification.json` (stratified; n>=30 required)

## Non-claims
- Not claiming zero false positives on live national PNCP objects outside gold.
