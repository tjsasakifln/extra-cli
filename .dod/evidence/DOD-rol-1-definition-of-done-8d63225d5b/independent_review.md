# Independent adversarial review — A versão do código é registrada.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-8d63225d5b` |
| **Requirement (DOD.md L920)** | A versão do código é registrada. |
| **Reviewer** | adversarial-qa-continue-03 |
| **Reviewed at (UTC)** | 2026-07-21T23:45:00Z |
| **main_sha** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Verdict** | **FAIL** |

## Falsification attempts — SUCCEEDED

| Attack | Result |
|--------|--------|
| Only presence of `collect_run_metadata`? | **CONFIRMED FALSIFICATION.** Function returns `git_sha` via `git rev-parse HEAD`, but **is never called** from the golden path CLI/`_save_final_ledger` path. Grep of `scripts/`: sole definition at L292; no production call sites. |
| Is `git_sha` in persisted ledger? | **NO.** Reproof `ledger-meta.json`, `ledger-snap.json`, `ledger-reports.json` contain no `git_sha` / `code_version` field. `RunRecord` dataclass has no metadata field. |
| Does `proof.json` invent evidence? | **YES.** `"git_sha": "432da028…"` is the campaign `main_sha`, not a field read from a ledger artifact. |
| Is acceptance_criteria honest? | **STALE.** Still claims `git_sha=05dcb88a2b0186f54220ba898569aceaeb12f5f8` (pre-#85 base). |
| Test proves registration? | **NO.** `test_metadata_includes_code_and_schema_version` only calls the pure helper in-process; does not assert ledger persistence. |

## Campaign critical-path criterion (pre-stated)

> Accept if wired into persisted ledger on main  
> (`docs/ops/campaigns/…/tracks/critical-path.md`)

**Not met.** Helper exists; registration into the run ledger does **not**.

## Required for PASS_FOR_ACCEPT (guidance to @dev — not implemented by QA)

1. Call `collect_run_metadata` (or equivalent) inside `_save_final_ledger` / `RunRecord`
2. Persist `git_sha` on the written ledger JSON
3. Integration test: CLI run → ledger contains non-empty `git_sha` (not `"unknown"` when git available)
4. Re-proof ledger on main with field present

## Decision

**FAIL** — requirement is *registrada* (recorded), not *calculável*. Presence of an unused collector function is not acceptance evidence.
