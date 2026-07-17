---
task: buildDependencyGraph()
responsavel: "@critical-path-roi-planner"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: requirements_matrix
    tipo: object
    origem: state/requirements/
    obrigatorio: true
  - campo: snapshot
    tipo: object
    origem: state/snapshots/
    obrigatorio: true

Saida:
  - campo: graph
    tipo: object
    destino: state/graphs/
    persistido: true
  - campo: critical_path
    tipo: array
    destino: Return
    persistido: true

Checklist:
  - [ ] Nodes for open DoD items and gates
  - [ ] Edges for hard dependencies
  - [ ] Critical path identified
  - [ ] External blockers marked

preconditions:
  - [ ] requirements matrix present

postconditions:
  - [ ] graph schema-valid

blockers:
  - none

tools:
  - filesystem

scripts:
  - scripts/graph_build.py

dependencies:
  - dod-truth-auditor-reconcile-dod-truth.md

parallelism: no
error_strategy: fail on cycles; else persist
retry: 0
persistence: state/graphs/
expected_cost: low-medium
---

# *build-dependency-graph

## Purpose

Construir/atualizar grafo de dependências entre requisitos, gates e trabalho técnico.

## Execution Steps

### Step 1 — Nodes from open requirements and gates
### Step 2 — Edges from docs (PRE-VPS, coverage, stories) + code deps
### Step 3 — Critical path via worker `scripts/graph_build.py`


## Error Handling

```yaml
error: GRAPH_CYCLE
cause: circular dependency detected
resolution: flag and break via human decision candidate
```


## Acceptance Criteria

  - [ ] Nodes for open DoD items and gates
  - [ ] Edges for hard dependencies
  - [ ] Critical path identified
  - [ ] External blockers marked

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
  - build-dependency-graph
```

---
*Task buildDependencyGraph() — extra-dod-roi*
