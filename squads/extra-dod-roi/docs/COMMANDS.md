# Commands — extra-dod-roi

| Command | Task | Mode |
|---------|------|------|
| `*status` | roi-orchestrator-show-status.md | read-only |
| `*scan-state` | codebase-cartographer-snapshot-project-state.md | read-only |
| `*audit-dod` | dod-truth-auditor-reconcile-dod-truth.md | read-only |
| `*rank-next` | critical-path-roi-planner-rank-unlocked-work-by-roi.md | read-only |
| `*explain-next` | critical-path-roi-planner-explain-next-best-action.md | read-only |
| `*plan-next` | critical-path-roi-planner-materialize-execution-card.md | read-only |
| `*verify-current` | adversarial-qa-auditor-run-adversarial-verification.md | read-only |
| `*show-blockers` | roi-orchestrator-show-blockers.md | read-only |
| `*execute-next` | delivery-engineer-implement-selected-slice.md | **write** |
| `*run-cycle` | roi-orchestrator-run-evergreen-roi-cycle.md | **write** |
| `*resume-cycle` | roi-orchestrator-resume-cycle.md | **write** |

CLI equivalents under `scripts/cli.py`.

## Fool-proof (v1.1)

| Command | Mode |
|---------|------|
| `*force-next` / `cli.py force-next` | write — ranking[0] + AIOX story Draft |
| `cli.py enforce <action>` | read-only gate |
| `cli.py cycle` | read-only state machine |
| `cli.py advance --to PHASE` | write — legal transitions only |

See `docs/FOOLPROOF.md`.
