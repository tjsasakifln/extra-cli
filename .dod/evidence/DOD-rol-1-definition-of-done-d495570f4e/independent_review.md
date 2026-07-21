# Independent adversarial review — A versão do schema é registrada.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-d495570f4e` |
| **Requirement (DOD.md L922)** | A versão do schema é registrada. |
| **Reviewer** | adversarial-qa-continue-03 |
| **Reviewed at (UTC)** | 2026-07-21T23:45:00Z |
| **main_sha** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Verdict** | **FAIL** |

## Falsification attempts — SUCCEEDED

| Attack | Result |
|--------|--------|
| Only presence of `schema_version` in helper? | **CONFIRMED.** `collect_run_metadata` returns `schema_version=migrations_count={N}` (file count under `db/migrations`, **not** DB `_migrations` ledger). Never invoked by CLI save path. |
| Field in reproof ledger? | **NO.** All three campaign ledgers lack `schema_version` / `migration_files_count`. |
| `proof.json` honest? | **`"schema_version": null`** — coordinator could not extract a real value from artifacts. Still marked `"ok": true` → inconsistent. |
| acceptance_criteria claim `migrations_count=62`? | Unit helper may return that when called; **not registered** on golden path runs. |
| DB schema version vs file count? | Even if wired, current helper is file-count proxy, not applied migration version from `public._migrations`. Residual for a future accept after wiring. |

## Campaign criterion

> Accept if wired (`critical-path.md`)

**Not met.**

## Required for PASS_FOR_ACCEPT

1. Persist schema identity on ledger (file count **or** preferably applied migration max from DB)
2. Integration test CLI → ledger field present
3. Re-proof with non-null value

## Decision

**FAIL** — schema version is not recorded on golden path execution artifacts.
