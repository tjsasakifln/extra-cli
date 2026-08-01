# TEST-REPORT — WORKBENCH-01

## Command Center suite

```bash
python3 -m pytest tests/command_center/ -q --tb=line --no-cov
# 64 passed
```

| Suite | Result |
|-------|--------|
| test_api_security.py | PASS |
| test_capability_contracts.py | PASS (all capabilities incl. workflows) |
| test_workbench_flows.py | PASS (9) — PDF/XLSX/manifest/bundle/API/review/DOD block |

## What tests prove (shipped path)

- `run_workflow` for Flows A–D writes valid manifest + primary PDF + XLSX
- Formula injection neutralized
- Decision rules REJECT/DEFER/ACCEPT hash
- API: list workflows, run Extra workflow job, manifest endpoint, xlsx preview, pdf kind, review ACCEPT with hashes
- DOD ACCEPT blocked

## Gaps

- Full Playwright 20 scenarios not extended in this wave
- axe automated gate not executed in CI here
- Live (non-fixture) Extra weekly / commercial router e2e still env-dependent
