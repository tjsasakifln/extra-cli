# SCOPE-SEPARATION

## Backup

```text
backup/pr-186-before-scope-cleanup → 483ab4b5214c79f02bb8700d1e4c6b91e578a1d8
```

Pushed to `origin/backup/pr-186-before-scope-cleanup`.

## Why pSEO appeared on #186

Commits on the mixed tip:

- `67e208e9` feat(pseo): add read-only public export…
- `12d4be7f` fix(ci): green PR #186 — ruff pseo…

## Strategy executed

1. Backup tip.
2. Rebuild `feat/extra-local-command-center` from `origin/main` with **tree of backup tip minus pSEO paths** (139 files).
3. Isolated pSEO durable export on `feat/pseo-export-isolated` → **PR #187**.

## Verification

```bash
git diff --name-only origin/main...HEAD | grep -E '(^|/)pseo(/|$)'
# (empty)
```

## pSEO home

- Branch: `feat/pseo-export-isolated` (PR #187)
- Also retained: `feat/pseo-durable-export`, backup tip
