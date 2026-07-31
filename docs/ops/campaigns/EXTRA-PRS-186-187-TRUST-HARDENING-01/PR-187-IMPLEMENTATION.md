# PR #187 Implementation — Trust Hardening

**Branch:** `feat/pseo-export-isolated`  
**Baseline HEAD:** `f2b54588304cad76c70fa1ea6cb40ac2b52ca1bd`

## Changes

### B1 Typed allowlists (fail closed)
- `scripts/pseo/models.py` — Pydantic v2 models with `extra="forbid"` for public artifacts.
- Pipeline validates each artifact before write; unexpected/forbidden fields raise.

### B2 Real JSON Schema
- `scripts/pseo/jsonschema_export.py` generates draft 2020-12 schema with `$defs` and `additionalProperties: false`.
- Written as `schema.json`. Human descriptor moved to `export-descriptor.json`.

### B3 Human approval gate
- `scripts/pseo/approval.py` — approval artifact bound to `dataset_hash`, `schema_version`, `exporter_version`, `source_commit_sha`.
- Without valid approval: `snapshot_status=CANDIDATE`, `indexable=false`, `publish_status=REVIEW_REQUIRED`.
- CLI: `--approval path/to/approval.json`. Template helper `write_approval_template`.

### B4 Privacy min-cell
- `scripts/pseo/privacy.py` — `min_cell_count=5`; small buyer cells bucketed as “outros”.
- Applied to market `top_buyers` before publish.

### B5 Chunked extraction
- `load_from_db` uses named server-side cursors + `fetchmany` (no `fetchall` on large tables).
- REPEATABLE READ, read-only, `statement_timeout`, `application_name=extra-pseo-export`.

### B6 Atomic write
- `scripts/pseo/atomic_io.py` — temp dir → validate → promote; prior snapshot preserved on failure.
- `CURRENT.json` pointer (no symlink dependency).

### B7–B8 Provenance / freshness
- Existing provenance retained; approval status recorded on manifest.
- Freshness still carries period bounds + by_dataset policies (not only generated_at).

### B10 Cross validations
- Pydantic ranges (non-negative counts/values), URL https-only, percentile ordering on markets.

### Ruff
- Import order / UP017 fixed (CI Lint was red on tip).

## Tests
- `tests/pseo/test_trust_hardening.py` (10 cases)
- Full suite: 44 passed
- Fixture export: validation ok, `indexable=false` without approval
