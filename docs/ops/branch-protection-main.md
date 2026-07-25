# Branch protection for `main`

Apply after governance gates land on `main`. Discover real check names from the latest green CI run; do not invent names.

## Required status checks (canonical CI)

From `.github/workflows/ci.yml` job `name:` fields:

- `Lint (ruff)`
- `Type Check (mypy)`
- `Test (critical readiness)`
- `Test operational expanded (PR)`
- `Test All (full suite)`
- `Resilience Gate (pre-VPS)`
- `Security (bandit)`
- `Dependency Audit (pip-audit)`
- `Generated Artifacts Policy`
- `PR Reviewability Policy`
- `Pytest Skip Policy`

## Apply via GitHub API

```bash
# Requires admin on tjsasakifln/extra-cli
REPO=tjsasakifln/extra-cli

gh api -X PUT "repos/${REPO}/branches/main/protection" \
  -H "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Lint (ruff)",
      "Type Check (mypy)",
      "Test (critical readiness)",
      "Test operational expanded (PR)",
      "Test All (full suite)",
      "Resilience Gate (pre-VPS)",
      "Security (bandit)",
      "Dependency Audit (pip-audit)",
      "Generated Artifacts Policy",
      "PR Reviewability Policy",
      "Pytest Skip Policy"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
EOF
```

Notes:

- `required_approving_review_count: 0` keeps a single-maintainer repo unblocked while still requiring conversation resolution and status checks.
- `strict: true` requires the branch to be up to date with `main` before merge.
- If the API returns non-2xx, capture HTTP status and re-run with admin credentials; do not fake `ENABLED`.

## Verify

```bash
gh api "repos/${REPO}/branches/main/protection" --jq '{
  strict: .required_status_checks.strict,
  contexts: .required_status_checks.contexts,
  force: .allow_force_pushes.enabled,
  deletions: .allow_deletions.enabled,
  conv: .required_conversation_resolution.enabled
}'
```
