# Generated Artifacts Policy

**Purpose:** Keep pull requests reviewable. Reproducible run outputs do not belong in Git.

## What MAY enter Git

| Category | Examples | Limits |
|----------|----------|--------|
| Source code | `scripts/**/*.py`, migrations, Makefile targets | n/a |
| Specs / ADRs / docs | `specs/**`, `docs/**`, architecture notes | n/a |
| Tests & small fixtures | `tests/**/fixtures/**` | **≤ 100 KiB per file** |
| Schemas / manifests | `schema.json`, `pack-manifest.json`, `manifest.json` | **≤ 256 KiB** |
| Checksums / freeze metadata | `checksums.json`, `user-acceptance.json` | **≤ 256 KiB** |
| Small evidence JSON | claims, non-claims, isolation, coverage, migrations proof | **≤ 256 KiB** |
| Human-readable status | `BLOCKED.md`, `PASS.md`, `REVIEW-*.md` | **≤ 256 KiB** |

## What MUST NOT enter Git (prohibited generated outputs)

| Category | Patterns / examples |
|----------|---------------------|
| Binary deliverables | `*.pdf`, `*.xlsx`, `*.xls`, `*.docx` under `artifacts/campaigns/**` |
| Full pack dumps | `pack-full.json`, `deliverable_*.json` (full A–E dumps), `cycle-state.json` |
| Large monitors | `monthly-monitor-live.json` |
| Duplicate run trees | `**/pack-rc/**`, `**/pack-verify/**` full copies |
| Dossier bodies | `**/dossiers/**/*.html`, large dossier JSON/CSV (keep at most one tiny fixture under `tests/`) |
| Bulk CSV extracts | expiring/price/competitors/opportunities CSV from live runs |
| Dumps / backups | `*.dump`, `*.sql.dump` |
| JUnit noise | `tests.xml` under campaign artifacts |
| Client private docs | any real client submission package |

**Hard size ceiling for any newly added path under `artifacts/campaigns/**`:** **512 KiB** unless listed in the exception registry below.

## Directories discouraged for large blobs

- `artifacts/campaigns/*/pack/` — only checksums, manifests, short markdown
- `artifacts/campaigns/*/monthly/` — summaries only, not full state
- `artifacts/campaigns/*/dossiers/` — prefer regenerate; do not version full sets
- `output/` — runtime only (already largely gitignored)

## Exceptions

Exceptions require:

1. Explicit entry in `docs/generated-artifacts-exceptions.json` (path + reason + max_bytes + owner)
2. Review in the PR description
3. No private client data

Built-in always-allowed (no registry entry):

- `**/user-acceptance.json`
- `**/claims.json`, `**/non-claims.json`
- `**/checksums.json`, `**/pack-manifest.json`
- `**/migrations.json`, `**/isolation.json`
- `docs/**`, `specs/**`, `tests/**` within size limits above

## Retention & reproduction

1. Generate outputs via documented Makefile / CLI targets on **isolated** Postgres only.
2. Upload pack outputs as **GitHub Actions artifacts** (retention ≤ 14 days) when CI needs them.
3. Optional: external object storage with checksum recorded in Git.
4. Audit a run: re-run pipeline → compare to `checksums.json` → do not re-commit binaries.

## Privacy

- Never commit real client proposal documents, credentials, or PII dumps.
- Fictional fixtures for experimental packs must be labeled fictional.
- Redact before any exception request.

## How to download CI artifacts

```text
GitHub → Actions → select workflow run → Artifacts → download zip
# or
gh run download <run-id> -n <artifact-name>
```

## Enforcement

Gate script: `python -m scripts.ops.check_generated_artifacts_policy`

- Runs in CI job **Generated Artifacts Policy**.
- Compares added/changed files in the PR (or `git diff --name-only origin/main...HEAD`).
- Exit code **0** = pass; **1** = policy violation (fail-closed).
- Does **not** use `|| true`, skip, or soft-fail.

## Audit checklist (reviewers)

- [ ] No new PDF/XLSX under `artifacts/campaigns`
- [ ] No file > 512 KiB under campaign artifacts without exception
- [ ] Checksums/manifests still present for freeze/acceptance
- [ ] Regeneration instructions exist (`REPRODUCIBLE-OUTPUTS.md` or Makefile)
