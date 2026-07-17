---
task: rankUnlockedWorkByRoi()
responsavel: "@critical-path-roi-planner"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: candidates
    tipo: array
    origem: Context
    obrigatorio: false
  - campo: weights_path
    tipo: string
    origem: File
    obrigatorio: false
    validacao: "data/roi-weights.yaml"
  - campo: top_n
    tipo: number
    origem: User Input
    obrigatorio: false
  - campo: readonly
    tipo: boolean
    origem: User Input
    obrigatorio: false
    validacao: "default true for *rank-next"

Saida:
  - campo: ranking
    tipo: array
    destino: state/rankings/
    persistido: true
  - campo: selected
    tipo: object
    destino: Return
    persistido: true
  - campo: discarded_attractive
    tipo: array
    destino: Return
    persistido: true
  - campo: divergences
    tipo: array
    destino: Return
    persistido: true

Checklist:
  - [ ] Only UNLOCKED candidates scored
  - [ ] Dimensions 0-5 with documented weights
  - [ ] Causal justification for #1
  - [ ] Attractive-but-rejected explained
  - [ ] Top 5 presented for *rank-next
  - [ ] No product/DoD mutations

preconditions:
  - [ ] weights file present
  - [ ] can build snapshot if missing

postconditions:
  - [ ] ranking persisted under squad state only
  - [ ] product tree clean of task side-effects

blockers:
  - none

tools:
  - filesystem
  - git
  - gh optional

scripts:
  - scripts/rank_next_cli.py
  - scripts/score_roi.py
  - scripts/snapshot_state.py
  - scripts/parse_dod.py
  - scripts/graph_build.py

dependencies:
  - critical-path-roi-planner-generate-candidate-work.md (or composed pipeline)

parallelism: no
error_strategy: empty ranking with blockers
retry: 0
persistence: state/rankings/ (optional in pure stdout mode)
expected_cost: medium (~1-5min)
---

# *rank-unlocked-work-by-roi

## Purpose

Pontuar e ordenar trabalho desbloqueado por ROI configurável; entrada principal de *rank-next (read-only).

## Execution Steps

### Step 1 — Ensure snapshot + truth + graph + candidates (compose or load if fresh)
### Step 2 — Filter UNLOCKED
### Step 3 — Score via `scripts/score_roi.py` and `scripts/rank_next_cli.py`
### Step 4 — Sensitivity ±1 on top dimensions
### Step 5 — Emit top N + selected slice for execute-next


## Error Handling

```yaml
error: RANK_EMPTY
cause: no unlocked work
resolution: NO_UNLOCKED_WORK outcome; show blockers
```


## Acceptance Criteria

  - [ ] Only UNLOCKED candidates scored
  - [ ] Dimensions 0-5 with documented weights
  - [ ] Causal justification for #1
  - [ ] Attractive-but-rejected explained
  - [ ] Top 5 presented for *rank-next
  - [ ] No product/DoD mutations

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
  - rank-unlocked-work-by-roi
```

---
*Task rankUnlockedWorkByRoi() — extra-dod-roi*
