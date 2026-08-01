# PR #187 Classifier Report

## Gates (enforced in unit tests **and** export path)

| Gate | Threshold | Where |
|------|-----------|--------|
| Global precision `aec_confirmed` | **>= 0.97** | `test_gold_precision_gate` + `run_gold_classifier_gate` |
| Global false positives | **fp == 0** | same |
| Per-segment precision | **>= 0.95** (segments with n>=3 and predicted positives) | same |
| Gold size | **n >= 30** | `run_gold_classifier_gate` / `gates.n_ok` |

`evaluate_classifier` returns `by_segment` metrics and `gates.publish_ok`.

## Export-path enforcement (B9)
- `write_export` calls `run_gold_classifier_gate()` **before** allowing `snapshot_status=PUBLISH_READY`
- Human approval alone is insufficient; failed classifier gate → `CLASSIFIER_GATE_FAILED` / `CANDIDATE`
- Manifest records `classifier_gate.{ok,reason,metrics,gold_path}`
- Tests:
  - `test_run_gold_classifier_gate_calls_evaluate_classifier`
  - `test_write_export_classifier_gate_blocks_publish_even_with_approval`
  - `test_write_export_with_valid_approval_marks_publish_ready` (requires gate ok)

## Gold set
- `tests/pseo/fixtures/gold_classification.json` (stratified; n>=30 required)

## Non-claims
- Not claiming zero false positives on live national PNCP objects outside gold.
- Not claiming production human APPROVED artifact exists (tests only).
