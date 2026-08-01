# BASELINE — EXTRA-COMMAND-CENTER-REAL-PIPELINES-01

## PR tip observed at mission start

- PR: #186
- Branch: `feat/extra-local-command-center`
- HEAD: `483ab4b5214c79f02bb8700d1e4c6b91e578a1d8`
- pytest command_center: 71 passed
- Playwright: 26 passed
- CI + Reviewability: success

## Problems

1. pSEO files mixed into PR #186 diff
2. Guided flows fixture-only; `use_fixture=False` rejected instead of running real pipelines
3. Workbench was demo cabin, not operational cockpit

## Constraints

- Do not touch web-cfg / Netlify production pSEO snapshot
- Max 2 PRs (pSEO isolated + #186)
- No auto-outreach / no auto-DOD accept
