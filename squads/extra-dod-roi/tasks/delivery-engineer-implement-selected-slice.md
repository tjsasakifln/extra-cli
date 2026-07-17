---
task: implementSelectedSlice()
responsavel: "@delivery-engineer"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: write
version: 1.0.0

Entrada:
  - campo: execution_card
    tipo: object
    origem: state/execution-cards/
    obrigatorio: true
  - campo: write_permission
    tipo: boolean
    origem: User Input
    obrigatorio: true
    validacao: "must be true"

Saida:
  - campo: branch
    tipo: string
    destino: Return
    persistido: true
  - campo: commits
    tipo: array
    destino: Return
    persistido: true
  - campo: test_results
    tipo: object
    destino: state/evidence/
    persistido: true
  - campo: handoff_to_qa
    tipo: object
    destino: state/handoffs/
    persistido: true

Checklist:
  - [ ] Branch not main
  - [ ] Only authorized files touched
  - [ ] Tests added/updated
  - [ ] Local lint/type/tests run
  - [ ] Atomic commits
  - [ ] DoD checkboxes NOT updated
  - [ ] Handoff to QA written

preconditions:
  - [ ] write_permission true
  - [ ] execution card complete
  - [ ] readiness checklist pass
  - [ ] no lock conflict

postconditions:
  - [ ] implementer tests recorded
  - [ ] ready for adversarial QA

blockers:
  - write_permission
  - credentials if required by card

tools:
  - git
  - pytest
  - ruff
  - mypy
  - make

scripts:


dependencies:
  - critical-path-roi-planner-materialize-execution-card.md

parallelism: subagents only with clear file ownership
error_strategy: abort and leave branch for resume
retry: 1 for flaky tests
persistence: state/handoffs/ + git branch
expected_cost: high (varies)
---

# *implement-selected-slice

## Purpose

Implementar a fatia selecionada em branch isolada sem auto-aprovar qualidade ou DoD.

## Execution Steps

### Step 1 — Create branch/worktree from base (prefer main tip or agreed base)
### Step 2 — Implement minimal slice
### Step 3 — Run implementer verifications
### Step 4 — Commit atomically
### Step 5 — Write QA handoff (no DoD edits)


## Error Handling

```yaml
error: IMPLEMENT_BLOCKED
cause: missing secret / conflict
resolution: BLOCKED_EXTERNAL or CONFLICT_WITH_ACTIVE_WORK
```


## Acceptance Criteria

  - [ ] Branch not main
  - [ ] Only authorized files touched
  - [ ] Tests added/updated
  - [ ] Local lint/type/tests run
  - [ ] Atomic commits
  - [ ] DoD checkboxes NOT updated
  - [ ] Handoff to QA written

## Metadata

```yaml
version: 1.0.0
created: 2026-07-17
updated: 2026-07-17
author: Tiago Jun Sasaki
squad: extra-dod-roi
tags:
  - extra-dod-roi
  - evergreen
  - implement-selected-slice
```

---
*Task implementSelectedSlice() — extra-dod-roi*
