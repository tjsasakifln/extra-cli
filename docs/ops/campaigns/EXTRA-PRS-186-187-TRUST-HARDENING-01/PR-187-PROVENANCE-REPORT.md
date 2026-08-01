# PR #187 Provenance Report

## Manifest fields (retained + extended)
- `source_repository`, `source_commit_sha`, `source_branch`
- `export_entrypoint` / `exporter_entrypoint` = `python -m scripts.pseo.export_web_cfg`
- `export_version` / `exporter_version`
- `dataset_hash` (post privacy/validation body)
- `checksums` per file
- `approval` / `publish_status` / `indexable` / `snapshot_status`
- `classifier_gate` (B9: gold evaluate on export path before PUBLISH_READY)
- `freshness` with `data_period_*` and `by_dataset`

## B7 — commit + entrypoint (no short-circuit)
- `validate_export_dir(..., require_commit_entrypoint=True)` **always** checks:
  1. export entrypoint exists in working tree
  2. `source_commit_sha` present and not `unknown`
  3. `verify_commit_has_entrypoint(sha)` — commit reachable and contains export entry
- Presence of `scripts/pseo/cli_export.py` does **not** skip the above (fixed)
- Tests: `test_bogus_source_commit_sha_rejected_even_when_cli_export_exists`,
  `test_unknown_source_commit_sha_rejected`,
  `test_require_commit_entrypoint_true_on_promote_path`

## Approval binding
- Human approval required for `PUBLISH_READY` / `indexable=true`
- Mismatch on dataset_hash, schema_version, exporter_version, or source_commit_sha → `INVALID_APPROVAL`
- Classifier gold gate must also pass (`run_gold_classifier_gate` → `publish_ok`)

## Fixture run (this session)
- `source_commit_sha`: tip at export time
- `publish_status`: `REVIEW_REQUIRED`
- `snapshot_status`: `CANDIDATE`
- `indexable`: false
- `classifier_gate.ok`: true (gates evaluated; approval still required for publish)
