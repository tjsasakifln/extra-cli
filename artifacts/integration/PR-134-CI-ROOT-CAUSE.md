# PR #134 — Full suite CI root cause

## Evidence

- PR: https://github.com/tjsasakifln/extra-cli/pull/134  
- Failed job: **Test All (full suite)**  
- Run: https://github.com/tjsasakifln/extra-cli/actions/runs/30131433813  
- Other 7 jobs: SUCCESS  

## Root cause

```text
ERROR collecting tests/budget_audit/test_adversarial_property.py
ModuleNotFoundError: No module named 'hypothesis'
```

The module imports `hypothesis` at collection time. Full suite installs `requirements.txt`, which did **not** list `hypothesis`. Critical/operational jobs did not collect this path → green while full suite red.

This is **not** an acceptable “pre-existing unrelated failure” without the same SHA-base comparison; it is introduced by the PR’s new test module.

## Fix

1. Add `hypothesis` to `requirements.txt` (or ensure CI full-suite installs a declared test extra that includes it).  
2. Re-run full suite.  
3. Do not use `pytest.importorskip` solely to hide missing mandatory deps for CI-collected tests.

## Status

Fix applied on branch `campaign/engineering-budget-composition-bdi-audit-01` (see commits).  
Merge still **blocked** until full suite green and after #131 merge/rebase order.


## Post-fix status

- Commit `4c912519` added `hypothesis>=6.100.0` to `requirements.txt`.
- CI run after fix: **Test All (full suite) PASS** (run 30137611994).
- All 8 jobs green.
- Still **do not merge** until after #131 merge + rebase per integration order.
