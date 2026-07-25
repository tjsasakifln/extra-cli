# PR Reviewability Policy

Ready-for-review PRs must stay small, single-purpose, and proven on the exact HEAD SHA.

## Hard limits (ready PRs)

| Rule | Limit |
|------|-------|
| Changed files | ≤ **60** |
| Textual lines added | ≤ **10_000** |
| Product binaries / bulk generated outputs | **0** (see generated-artifacts policy) |
| Multi-capability mega-mix | **forbidden** |

### Multi-capability mix

A PR fails when it simultaneously changes:

1. migrations, **and**
2. CI / Makefile, **and**
3. runtime product code, **and**
4. commercial deliverable / pack paths

Decompose: foundation → linkage → integration → commercial pack.

### Draft PRs

Drafts may exceed file/line limits while being rebuilt. Binaries and generated bulk still fail.

### Consistency

- PR body must not claim a CI/HEAD SHA different from the tip under test.
- Declaring `PASS` / `CI_GREEN` / `READY_TO_MERGE` while required gates are missing fails the gate.

## Exceptions

File: `docs/pr-reviewability-exceptions.json`

```json
{
  "active": {
    "reason": "...",
    "owner": "name",
    "deadline": "YYYY-MM-DD",
    "approved_by": "human",
    "waives": ["too_many_files"]
  }
}
```

Incomplete exceptions fail closed.

## Enforcement

```bash
python -m scripts.ops.check_pr_reviewability --base origin/main
# draft:
python -m scripts.ops.check_pr_reviewability --base origin/main --draft
```

CI job: **PR Reviewability Policy** (fail-closed).

## Branch protection (operators)

See `docs/ops/branch-protection-main.md` for the exact `gh api` commands. Required check names must match workflow job `name:` fields exactly.
