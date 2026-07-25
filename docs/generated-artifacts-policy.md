# Generated Artifacts Policy

**Purpose:** Keep pull requests reviewable. Reproducible run outputs do not belong in Git.

## What MAY enter Git

| Category | Examples | Limits |
|----------|----------|--------|
| Source code | `scripts/**/*.py`, migrations, Makefile targets | n/a |
| Specs / ADRs / docs | `specs/**`, `docs/**`, architecture notes | n/a |
| Tests & small fixtures | `tests/**/fixtures/**` | **≤ 100 KiB per file**; prefer builders |
| Schemas / small evidence JSON | `manifest.json`, `checksums.json`, isolation/coverage proofs | **≤ 256 KiB** |
| Human-readable status | `BLOCKED.md`, short review notes | **≤ 256 KiB** |

## What MUST NOT enter Git

| Category | Patterns / examples |
|----------|---------------------|
| Binary deliverables | `*.pdf`, `*.xlsx`, `*.xls`, `*.docx` (outside tiny test fixtures) |
| Full pack dumps | `pack-full.json`, `deliverable_*.json`, `cycle-state.json` |
| Large monitors / reports | rendered HTML, bulk CSV, junit `tests.xml` under campaigns |
| Runtime output | anything under `output/` |
| Dumps / backups | `*.dump`, SQL dumps |
| Logs | `*.log` |
| Private client docs | real client submission packages, PII |

**Hard size ceiling for any newly added path under `artifacts/campaigns/**`:** **512 KiB** unless listed in the exception registry.

## Exceptions (fail-closed)

Every exception in `docs/generated-artifacts-exceptions.json` **must** include:

| Field | Meaning |
|-------|---------|
| `path` | Exact repo-relative path |
| `reason` | Why Git must hold this blob |
| `owner` | Human accountable |
| `deadline` | `YYYY-MM-DD` expiry |
| `max_bytes` | Hard size cap |

Silent exceptions are rejected by the gate. Prefer **fixture builders** and **GitHub Actions artifacts** (retention ≤ 14–30 days).

## Enforcement

```bash
python -m scripts.ops.check_generated_artifacts_policy --base origin/main
```

- CI job: **Generated Artifacts Policy**
- Diff vs real PR base (or `origin/main`) — only paths introduced/changed by the PR
- Exit **0** pass / **1** fail — **no** `continue-on-error`, **no** `|| true`

## Reproduction

1. Generate outputs via Makefile / CLI on isolated Postgres only.
2. Upload heavy packs as Actions artifacts when CI needs them.
3. Record checksums in Git; do not re-commit binaries.
