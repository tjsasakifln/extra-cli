# Data model — 008 (local CC SQLite + filesystem)

## Existing tables (store.py)

- `jobs`, `job_logs`, `audit`, `preferences`, `human_decisions`, `review_items`, `favorites`

## Logical product entities (filesystem + job payload)

| Entity | Storage |
|--------|---------|
| Workspace | implicit local CC data_dir |
| Client/frente | workflow.client_id |
| Project/campaign | run under jobs/{job_id}/deliverables |
| Run | RunManifest.run_id + job_id |
| Artifact | files + manifest.artifacts[] with roles |
| ReviewTask | review_items + payload.artifact_hashes |
| Decision | human_decisions.payload hashes/version |
| ExportBundle | ZIP + export-bundle-manifest.json |

## Artifact roles

primary_deliverable, workbook, executive_report, evidence, source_data, manifest, log, attachment, review_package
