---
task: showStatus()
responsavel: "@roi-orchestrator"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: verbose
    tipo: boolean
    origem: User Input
    obrigatorio: false

Saida:
  - campo: status
    tipo: object
    destino: Return
    persistido: false

Checklist:
  - [ ] Cycle lock state
  - [ ] Last snapshot identity
  - [ ] Last ranking top-1
  - [ ] Open blockers count

preconditions:
  - [ ] squad installed

postconditions:
  - [ ] no mutations

blockers:
  - none

tools:
  - filesystem

scripts:
  - scripts/cli.py

dependencies:
  - none

parallelism: yes
error_strategy: report empty
retry: 0
persistence: none
expected_cost: low
---

# *show-status

## Purpose

Status operacional do squad e ciclo (read-only).

## Execution Steps

### Read state/* and print summary

## Error Handling

```yaml
error: STATE_MISSING
cause: never run
resolution: suggest *scan-state / *rank-next
```

## Acceptance Criteria

  - [ ] Cycle lock state
  - [ ] Last snapshot identity
  - [ ] Last ranking top-1
  - [ ] Open blockers count

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
  - show-status
```

---
*Task showStatus() — extra-dod-roi*
