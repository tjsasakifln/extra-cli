# Branch protection proposal for `main`

## Current state (evidence)

```text
GET /repos/tjsasakifln/extra-cli/branches/main/protection → 404 Branch not protected
```

## Proposed settings (do not apply silently)

| Setting | Value |
|---------|--------|
| Require pull request before merging | yes |
| Required approving reviews | ≥ 1 for integration PRs |
| Dismiss stale reviews | yes |
| Require conversation resolution | yes |
| Require status checks | yes, up to date |
| Required checks | Lint (ruff), Type Check (mypy), Test All (full suite), Test (critical readiness), Resilience Gate, Security (bandit), Dependency Audit (pip-audit), Generated Artifacts Policy |
| Require branches up to date | yes |
| Restrict force push | yes |
| Restrict deletions | yes |
| Allow admin bypass | optional, discouraged |

## CODEOWNERS proposal

```text
# .github/CODEOWNERS (proposal)
/db/migrations/ @tjsasakifln
/.github/workflows/ @tjsasakifln
/scripts/linkage/ @tjsasakifln
/scripts/ops/live_consulting_pack.py @tjsasakifln
/scripts/ops/check_generated_artifacts_policy.py @tjsasakifln
/docs/generated-artifacts-policy.md @tjsasakifln
```

Apply only with explicit admin action and audit note in this folder.
