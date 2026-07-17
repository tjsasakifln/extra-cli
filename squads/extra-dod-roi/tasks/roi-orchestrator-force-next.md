---
task: forceNextRoiAioxCycle()
responsavel: "@roi-orchestrator"
responsavel_type: agent
atomic_layer: organism
elicit: false
mode: write
version: 1.1.0
foolproof: true

Entrada:
  - campo: write_permission
    tipo: boolean
    origem: User Input
    obrigatorio: true
    validacao: "must be true"
  - campo: fetch_remote
    tipo: boolean
    origem: User Input
    obrigatorio: false

Saida:
  - campo: cycle
    tipo: object
    destino: state/cycles/current.json
    persistido: true
  - campo: selected_id
    tipo: string
    destino: Return
    persistido: true
  - campo: story_id
    tipo: string
    destino: docs/stories/ + .aiox/state/stories/
    persistido: true
  - campo: mandatory_steps
    tipo: array
    destino: Return
    persistido: false

Checklist:
  - "[ ] Fresh rank computed (not stale)"
  - "[ ] ranking[0] only selected"
  - "[ ] Execution card bound to selected_id"
  - "[ ] AIOX story Draft + state materialized"
  - "[ ] Cycle phase = STORY_DRAFT"
  - "[ ] Implementation NOT started"
  - "[ ] Mandatory AIOX steps printed"
  - "[ ] No DoD checkbox changes"

preconditions:
  - "[ ] write_permission true"
  - "[ ] git repo accessible"
  - "[ ] DOD.md readable"

postconditions:
  - "[ ] cycle.foolproof == true"
  - "[ ] story status Draft until @po"
  - "[ ] enforce implement fails until Ready"

blockers:
  - "NO_UNLOCKED_WORK"
  - "LOCK_HELD"
  - "STALE only auto-fixed by re-rank inside force-next"

tools:
  - git
  - filesystem

scripts:
  - scripts/force_next.py
  - scripts/rank_next_cli.py
  - scripts/materialize_aiox_story.py
  - scripts/cycle_state.py
  - scripts/cycle_lock.py
  - scripts/enforce_aiox_path.py

dependencies:
  - critical-path-roi-planner-rank-unlocked-work-by-roi.md

parallelism: no
error_strategy: abort with named code; never invent alternate work
retry: 0
persistence: state/cycles/ + state/execution-cards/ + docs/stories/ + .aiox/state/stories/
expected_cost: medium
---

# *force-next

## Purpose

**Única entrada fool-proof** para avançar o projeto: recalcula ROI, trava no ranking[0],
materializa story AIOX Draft e **obriga** a sequência:

`@po -> @dev -> @qa -> @po -> @devops -> force-next (rerank)`

Não implementa código. Não auto-Ready. Não auto-QA. Não auto-merge.

## Execution Steps

### Step 1

```bash
python squads/extra-dod-roi/scripts/force_next.py
# or
python squads/extra-dod-roi/scripts/cli.py force-next
```

### Step 2 — stop for @po

Never call implement until:

```bash
python squads/extra-dod-roi/scripts/enforce_aiox_path.py implement
# must return ok:true (requires po_validated + Ready)
```

### Step 3 — after full SDC

```bash
python squads/extra-dod-roi/scripts/cli.py force-next
```

## Error Handling

```yaml
error: NO_UNLOCKED_WORK
cause: no UNLOCKED candidates
resolution: show blockers; do not invent work
```

```yaml
error: WRONG_CANDIDATE
cause: attempt to work non-#1 item
resolution: abort; only ranking[0]
```

## Metadata

```yaml
version: 1.1.0
author: Tiago Jun Sasaki
squad: extra-dod-roi
tags:
  - foolproof
  - aiox
  - force-next
```
