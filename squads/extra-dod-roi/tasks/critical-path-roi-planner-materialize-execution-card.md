---
task: materializeExecutionCard()
responsavel: "@critical-path-roi-planner"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: selected
    tipo: object
    origem: state/rankings/
    obrigatorio: true

Saida:
  - campo: execution_card
    tipo: object
    destino: state/execution-cards/
    persistido: true
  - campo: aiox_story_stub
    tipo: object
    destino: Return
    persistido: false

Checklist:
  - [ ] Card includes DoD ref, evidence of problem, ROI justification
  - [ ] Alternatives discarded listed
  - [ ] AC, test commands, rollback, allowed/forbidden claims
  - [ ] Agents and handoff plan present

preconditions:
  - [ ] selected candidate exists

postconditions:
  - [ ] card matches template templates/execution-card.md

blockers:
  - none

tools:
  - filesystem

scripts:


dependencies:
  - critical-path-roi-planner-rank-unlocked-work-by-roi.md

parallelism: no
error_strategy: abort if incomplete
retry: 0
persistence: state/execution-cards/
expected_cost: low
---

# *materialize-execution-card

## Purpose

Transformar a decisão de ranking em execution card verificável e opcionalmente story/task AIOX.

## Execution Steps

### Step 1 — Fill template from selected candidate
### Step 2 — Attach test commands and rollback
### Step 3 — Persist under state/execution-cards/


## Error Handling

```yaml
error: CARD_INCOMPLETE
cause: missing AC or DoD ref
resolution: abort implement; return to rank
```


## Acceptance Criteria

  - [ ] Card includes DoD ref, evidence of problem, ROI justification
  - [ ] Alternatives discarded listed
  - [ ] AC, test commands, rollback, allowed/forbidden claims
  - [ ] Agents and handoff plan present

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
  - materialize-execution-card
```

---
*Task materializeExecutionCard() — extra-dod-roi*
