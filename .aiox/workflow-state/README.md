# .aiox/workflow-state/

Runtime state directory for epic orchestration pipelines.

## Purpose

This directory is declared by `epic-orchestration.yaml` (line 180) as the canonical persistence location for epic pipeline state. However, the **runtime implementation** in `execute-epic-plan.md` writes state to `.aiox/epic-{epicId}-state.yaml` (YAML format) instead.

## Resolution

The **canonical runtime location** is `.aiox/epic-{epicId}-state.yaml` (YAML format), matching the implementation in `execute-epic-plan.md`.

This directory exists to satisfy the `epic-orchestration.yaml` template declaration and to reserve the path for future consolidation if the JSON format is adopted.

## Contents

| File | Format | Purpose |
|------|--------|---------|
| `README.md` | Markdown | This file — directory documentation |

## Future

If the runtime implementation is updated to match the template declaration, this directory will hold:
- `{epicId}-pipeline.json` — JSON-format state for each epic pipeline
- `{epicId}-pipeline.json.bak` — Backup before writes (per `execute-epic-plan.md` error handling)

## Reference

- Template declaration: `.aiox-core/development/workflows/epic-orchestration.yaml` (state.persistence)
- Runtime implementation: `.aiox-core/development/tasks/execute-epic-plan.md`
- Runtime override: `.aiox/gotchas.json` → `epic_orchestration.state_file_mismatch`
