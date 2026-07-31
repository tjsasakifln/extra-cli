# PR #187 Provenance Report

## Manifest fields (retained + extended)
- `source_repository`, `source_commit_sha`, `source_branch`
- `export_entrypoint` / `exporter_entrypoint` = `python -m scripts.pseo.export_web_cfg`
- `export_version` / `exporter_version`
- `dataset_hash` (post privacy/validation body)
- `checksums` per file
- `approval` / `publish_status` / `indexable` / `snapshot_status`
- `freshness` with `data_period_*` and `by_dataset`

## Approval binding
- Human approval required for `PUBLISH_READY` / `indexable=true`
- Mismatch on dataset_hash, schema_version, exporter_version, or source_commit_sha → `INVALID_APPROVAL`

## Fixture run (2026-07-31)
- `source_commit_sha`: branch tip at export time
- `publish_status`: `REVIEW_REQUIRED`
- `snapshot_status`: `CANDIDATE`
- `indexable`: false
