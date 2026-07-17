---
task: generateCandidateWork()
responsavel: "@critical-path-roi-planner"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: graph
    tipo: object
    origem: state/graphs/
    obrigatorio: true
  - campo: snapshot
    tipo: object
    origem: state/snapshots/
    obrigatorio: true
  - campo: requirements_matrix
    tipo: object
    origem: state/requirements/
    obrigatorio: true

Saida:
  - campo: candidates
    tipo: array
    destino: Return
    persistido: true
  - campo: blocked
    tipo: array
    destino: state/blockers/
    persistido: true

Checklist:
  - [ ] Candidates have verifiable AC
  - [ ] Duplicates of open PR/branch excluded or flagged
  - [ ] Blocked items include owner, cause, unlock condition
  - [ ] Out-of-scope work excluded

preconditions:
  - [ ] graph + matrix available

postconditions:
  - [ ] each candidate has id, dod_ref, ac, deps

blockers:
  - none

tools:
  - filesystem
  - gh optional

scripts:
  - scripts/graph_build.py

dependencies:
  - critical-path-roi-planner-build-dependency-graph.md

parallelism: no
error_strategy: empty list ok
retry: 0
persistence: state/blockers/ + ranking input
expected_cost: medium
---

# *generate-candidate-work

## Purpose

Gerar candidatos de trabalho a partir do grafo e da verdade DoD, sem desbloquear artificialmente.

## Execution Steps

### Step 1 — Walk open/partial/not_ready nodes
### Step 2 — Apply unlock filters (resources, secrets, scope, reverseability)
### Step 3 — Detect PR/branch duplication from snapshot
### Step 4 — Emit blocked register for external bottlenecks


## Error Handling

```yaml
error: NO_CANDIDATES
cause: nothing unlocked
resolution: outcome NO_UNLOCKED_WORK; list blockers
```


## Acceptance Criteria

  - [ ] Candidates have verifiable AC
  - [ ] Duplicates of open PR/branch excluded or flagged
  - [ ] Blocked items include owner, cause, unlock condition
  - [ ] Out-of-scope work excluded

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
  - generate-candidate-work
```

---
*Task generateCandidateWork() — extra-dod-roi*
