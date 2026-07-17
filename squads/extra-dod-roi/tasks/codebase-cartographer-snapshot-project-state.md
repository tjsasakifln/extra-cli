---
task: snapshotProjectState()
responsavel: "@codebase-cartographer"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: repo_root
    tipo: string
    origem: Context
    obrigatorio: true
    validacao: "path exists"
  - campo: include_remote
    tipo: boolean
    origem: User Input
    obrigatorio: false
    validacao: "fetch --prune only, no checkout main"
  - campo: write_state
    tipo: boolean
    origem: User Input
    obrigatorio: false
    validacao: "if true write under squads/extra-dod-roi/state/snapshots only"

Saida:
  - campo: snapshot
    tipo: object
    destino: state/snapshots/
    persistido: true
  - campo: head
    tipo: string
    destino: Return
    persistido: false
  - campo: open_prs
    tipo: array
    destino: Return
    persistido: false
  - campo: dod_hash
    tipo: string
    destino: Return
    persistido: false

Checklist:
  - [ ] HEAD, branch, dirty files collected
  - [ ] origin refs updated without modifying main working tree
  - [ ] Open PRs/branches/CI status inventoried (best-effort)
  - [ ] DOD.md hash computed
  - [ ] Modules/tests/migrations/Makefile/CI paths listed
  - [ ] Concurrent work mapped
  - [ ] Snapshot JSON schema-valid
  - [ ] No product files modified

preconditions:
  - [ ] repo is a git repository
  - [ ] squad path exists
  - [ ] read access to DOD.md and docs/

postconditions:
  - [ ] snapshot object complete with timestamp and git identity
  - [ ] no product tree mutations

blockers:
  - none

tools:
  - git
  - gh (optional)
  - filesystem

scripts:
  - scripts/snapshot_state.py

dependencies:
  - none

parallelism: yes (with independent read tasks)
error_strategy: partial-ok with confidence flag
retry: 1 on transient network
persistence: state/snapshots/
expected_cost: low (~30-90s)
---

# *snapshot-project-state

## Purpose

Reconstruir o estado real e atual da codebase e da superfície de entrega (git, PRs, CI, artefatos) sem declarar itens do DoD concluídos.

## Execution Steps

### Step 1 — Collect git identity
Run `scripts/snapshot_state.py` (worker). Capture branch, HEAD, main HEAD, dirty list.

### Step 2 — Remote and concurrent work
`git fetch --prune` (optional). List branches and open PRs via `gh` if available.

### Step 3 — Structural inventory
Inventory scripts/, tests/, migrations, Makefile targets, CI workflows, docs/operations.

### Step 4 — Persist
Write `state/snapshots/{iso}-snapshot.json`. Never mark DoD items.


## Error Handling

```yaml
error: SNAPSHOT_PARTIAL
cause: gh/network unavailable
resolution: continue with local-only snapshot; flag confidence=partial
recovery: rank-next must disclose partial remote visibility
```


## Acceptance Criteria

  - [ ] HEAD, branch, dirty files collected
  - [ ] origin refs updated without modifying main working tree
  - [ ] Open PRs/branches/CI status inventoried (best-effort)
  - [ ] DOD.md hash computed
  - [ ] Modules/tests/migrations/Makefile/CI paths listed
  - [ ] Concurrent work mapped
  - [ ] Snapshot JSON schema-valid
  - [ ] No product files modified

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
  - snapshot-project-state
```

---
*Task snapshotProjectState() — extra-dod-roi*
