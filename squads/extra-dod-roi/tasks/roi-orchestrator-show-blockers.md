---
task: showBlockers()
responsavel: "@roi-orchestrator"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: include_resolved
    tipo: boolean
    origem: User Input
    obrigatorio: false

Saida:
  - campo: blockers
    tipo: array
    destino: Return
    persistido: false

Checklist:
  - [ ] Each blocker has owner, cause, evidence, unlock condition, next test, alternate local ROI

preconditions:
  - [ ] optional prior audit

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
error_strategy: empty ok
retry: 0
persistence: none
expected_cost: low
---

# *show-blockers

## Purpose

Listar trabalho BLOCKED com condições de desbloqueio.

## Execution Steps

### Load state/blockers and matrix blocked rows

## Error Handling

```yaml
error: NONE
```

## Acceptance Criteria

  - [ ] Each blocker has owner, cause, evidence, unlock condition, next test, alternate local ROI

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
  - show-blockers
```

---
*Task showBlockers() — extra-dod-roi*
