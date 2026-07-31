# HANDOFF — WORKBENCH-01

## State

- PR: [#186](https://github.com/tjsasakifln/extra-cli/pull/186)
- Branch: `feat/extra-local-command-center`
- Terminal: **`PASS_COMMAND_CENTER_CONSULTING_WORKBENCH`**
- Pin: after smudge, `result.json` `head_sha` **and** `evidence_head` == `git rev-parse HEAD`

## Reproduce

```bash
git config filter.embedhead.smudge "python3 scripts/command_center/result_head_filter.py smudge"
git config filter.embedhead.clean "python3 scripts/command_center/result_head_filter.py clean"
git checkout HEAD -- docs/ops/campaigns/EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01/result.json
python3 -m pytest tests/command_center/ -q --tb=line --no-cov   # 70
cd apps/command-center && CC_OPEN_BROWSER=0 npm run test:e2e      # 26
```

## Key paths

- Backend: `scripts/command_center/`
- SPA: `apps/command-center/`
- Spec: `specs/008-command-center-consulting-workbench/`
- Campaign: `docs/ops/campaigns/EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01/`

## Do not

- Create second Command Center
- Bypass `confenge_commercial_target_router`
- Auto-accept DOD or auto-outreach
- Claim PASS if pytest/e2e/CI fail on tip or head_sha ≠ HEAD
