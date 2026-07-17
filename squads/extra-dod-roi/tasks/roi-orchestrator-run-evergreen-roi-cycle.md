---
task: runEvergreenRoiCycle()
responsavel: "@roi-orchestrator"
responsavel_type: agent
atomic_layer: organism
elicit: false
mode: write
version: 1.0.0

Entrada:
  - campo: write_permission
    tipo: boolean
    origem: User Input
    obrigatorio: true
  - campo: max_rework
    tipo: number
    origem: User Input
    obrigatorio: false

Saida:
  - campo: outcome
    tipo: string
    destino: state/cycles/
    persistido: true
  - campo: cycle_report
    tipo: object
    destino: state/cycles/
    persistido: true
  - campo: next_best
    tipo: object
    destino: Return
    persistido: true

Checklist:
  - [ ] Lock acquired and released
  - [ ] All mandatory phases attempted or short-circuited with named outcome
  - [ ] Outcome in allowed set
  - [ ] Next ROI indicated

preconditions:
  - [ ] write_permission true
  - [ ] working tree assessed
  - [ ] lock free or owned

postconditions:
  - [ ] lock released
  - [ ] outcome recorded

blockers:
  - none

tools:
  - git
  - gh
  - pytest
  - make

scripts:
  - scripts/cycle_lock.py
  - scripts/cli.py
  - scripts/stale_detect.py

dependencies:
  - all phase tasks

parallelism: only independent sub-phases
error_strategy: named outcomes; rework loop max_rework
retry: per subtask policy
persistence: state/cycles/
expected_cost: high
---

# *run-evergreen-roi-cycle

## Purpose

Executar o workflow evergreen-roi-cycle de ponta a ponta com outcomes nomeados.

## Execution Steps

### Execute workflow `workflows/evergreen-roi-cycle.yaml`
Phases 1–27 as documented. Map failures to:
PASS | FAIL_REWORK | BLOCKED_EXTERNAL | BLOCKED_HUMAN_DECISION |
CONFLICT_WITH_ACTIVE_WORK | NO_UNLOCKED_WORK | ABORTED_UNSAFE_STATE


## Error Handling

```yaml
error: CYCLE_ABORTED
cause: unsafe state or lock
resolution: ABORTED_UNSAFE_STATE; leave diagnostics
```


## Acceptance Criteria

  - [ ] Lock acquired and released
  - [ ] All mandatory phases attempted or short-circuited with named outcome
  - [ ] Outcome in allowed set
  - [ ] Next ROI indicated

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
  - run-evergreen-roi-cycle
```

---
*Task runEvergreenRoiCycle() — extra-dod-roi*
