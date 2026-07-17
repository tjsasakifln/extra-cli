---
task: resumeCycle()
responsavel: "@roi-orchestrator"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: write
version: 1.0.0

Entrada:
  - campo: cycle_id
    tipo: string
    origem: User Input
    obrigatorio: false
  - campo: write_permission
    tipo: boolean
    origem: User Input
    obrigatorio: true

Saida:
  - campo: resumed_from_phase
    tipo: string
    destino: Return
    persistido: true
  - campo: outcome
    tipo: string
    destino: state/cycles/
    persistido: true

Checklist:
  - [ ] Stale state detection run
  - [ ] Resume from last durable phase
  - [ ] Re-validate preconditions
  - [ ] Do not skip QA after implement

preconditions:
  - [ ] write_permission
  - [ ] cycle state exists or reconstructible

postconditions:
  - [ ] lock handled
  - [ ] phase advanced or outcome set

blockers:
  - none

tools:
  - git
  - gh

scripts:
  - scripts/stale_detect.py
  - scripts/cycle_lock.py
  - scripts/cli.py

dependencies:
  - roi-orchestrator-run-evergreen-roi-cycle.md

parallelism: no
error_strategy: safe restart on stale
retry: 0
persistence: state/cycles/
expected_cost: varies
---

# *resume-cycle

## Purpose

Retomar ciclo interrompido entre sessões sem confiar só no chat history.

## Execution Steps

### Step 1 — stale_detect.py on HEAD/DOD/PRs
### Step 2 — If stale, invalidate and re-snapshot
### Step 3 — Resume workflow from last checkpoint


## Error Handling

```yaml
error: RESUME_STALE
cause: HEAD/DOD changed
resolution: invalidate ranking; restart from snapshot
```


## Acceptance Criteria

  - [ ] Stale state detection run
  - [ ] Resume from last durable phase
  - [ ] Re-validate preconditions
  - [ ] Do not skip QA after implement

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
  - resume-cycle
```

---
*Task resumeCycle() — extra-dod-roi*
