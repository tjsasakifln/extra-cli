---
task: reconcileDodTruth()
responsavel: "@dod-truth-auditor"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: snapshot
    tipo: object
    origem: state/snapshots/
    obrigatorio: true
  - campo: dod_path
    tipo: string
    origem: File
    obrigatorio: true
    validacao: "default DOD.md"

Saida:
  - campo: requirements_matrix
    tipo: object
    destino: state/requirements/
    persistido: true
  - campo: superseded_claims
    tipo: array
    destino: Return
    persistido: true
  - campo: allowed_claims
    tipo: array
    destino: Return
    persistido: true
  - campo: forbidden_claims
    tipo: array
    destino: Return
    persistido: true
  - campo: veto
    tipo: object
    destino: Return
    persistido: true

Checklist:
  - [ ] DOD.md parsed into identifiable requirements
  - [ ] Each item classified DONE|PARTIAL|BLOCKED|NOT_APPLICABLE|NOT_READY
  - [ ] Superseded claims detected (e.g. LOCAL_RESILIENCE_READY)
  - [ ] Insufficient evidence rejected
  - [ ] Allowed vs forbidden claims listed
  - [ ] No checkbox mutations

preconditions:
  - [ ] snapshot available or collectable
  - [ ] DOD.md readable

postconditions:
  - [ ] matrix persisted
  - [ ] no DoD file writes

blockers:
  - none

tools:
  - filesystem
  - git

scripts:
  - scripts/parse_dod.py

dependencies:
  - codebase-cartographer-snapshot-project-state.md (recommended)

parallelism: no (after snapshot)
error_strategy: abort-on-corrupt-dod; conservative on ambiguity
retry: 0
persistence: state/requirements/
expected_cost: medium (~1-3min)
---

# *reconcile-dod-truth

## Purpose

Reconstrução conservadora da verdade do DoD com poder de veto a falso verde.

## Execution Steps

### Step 1 — Parse
Worker `scripts/parse_dod.py` extracts checkbox items and recent supersession sections.

### Step 2 — Correlate
Map items to evidence paths, stories, code, tests from snapshot.

### Step 3 — Classify conservatively
Default NOT_READY when evidence weak. Apply truth rules from data/scope-guardrails.yaml.

### Step 4 — Veto
If READY seals contradicted by audit docs (e.g. PRE-VPS-FINAL-*), record veto.


## Error Handling

```yaml
error: TRUTH_AMBIGUOUS
cause: conflicting docs without executable evidence
resolution: choose conservative NOT_READY
```


## Acceptance Criteria

  - [ ] DOD.md parsed into identifiable requirements
  - [ ] Each item classified DONE|PARTIAL|BLOCKED|NOT_APPLICABLE|NOT_READY
  - [ ] Superseded claims detected (e.g. LOCAL_RESILIENCE_READY)
  - [ ] Insufficient evidence rejected
  - [ ] Allowed vs forbidden claims listed
  - [ ] No checkbox mutations

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
  - reconcile-dod-truth
```

---
*Task reconcileDodTruth() — extra-dod-roi*
