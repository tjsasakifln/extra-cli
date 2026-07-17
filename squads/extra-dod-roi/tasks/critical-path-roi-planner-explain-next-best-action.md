---
task: explainNextBestAction()
responsavel: "@critical-path-roi-planner"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: ranking
    tipo: object
    origem: state/rankings/
    obrigatorio: false

Saida:
  - campo: explanation
    tipo: object
    destino: Return
    persistido: false

Checklist:
  - [ ] Causal why #1 wins
  - [ ] Risks and deps
  - [ ] Why attractive alternatives lost
  - [ ] What execute-next would do

preconditions:
  - [ ] ranking available or recomputable read-only

postconditions:
  - [ ] human-readable explanation emitted

blockers:
  - none

tools:
  - filesystem

scripts:
  - scripts/rank_next_cli.py

dependencies:
  - critical-path-roi-planner-rank-unlocked-work-by-roi.md

parallelism: yes
error_strategy: explain empty state
retry: 0
persistence: optional
expected_cost: low
---

# *explain-next-best-action

## Purpose

Explicar a próxima melhor ação sem executar implementação.

## Execution Steps

### Step 1 — Load or recompute ranking
### Step 2 — Produce causal narrative
### Step 3 — State execute-next implications (no write)


## Error Handling

```yaml
error: NOTHING_TO_EXPLAIN
cause: empty ranking
resolution: explain blockers
```


## Acceptance Criteria

  - [ ] Causal why #1 wins
  - [ ] Risks and deps
  - [ ] Why attractive alternatives lost
  - [ ] What execute-next would do

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
  - explain-next-best-action
```

---
*Task explainNextBestAction() — extra-dod-roi*
