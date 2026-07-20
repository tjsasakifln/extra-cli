# Evidence hygiene (PR #52)

Large runtime outputs (PDF, XLSX, full decision CSVs, full snapshot JSON) are
**not** retained in git. They must be published as CI/workflow artifacts.

Retained in-repo:
- `checksums.json` / `decision_manifest.json` / `reconcile.json` / `calibration.json`
- `profile_status.*` / `snapshot_delta.json` / `human_review_queue.meta.json`
- logs and dod-map under `evidence/`

Canonical HTTP reconfirm sample metadata: `live-pack-http/`.
Offline fixture metadata only: `live-pack/`.

Rule: SKIPPED CI ≠ PASS; regenerated packs go to Actions artifacts.
