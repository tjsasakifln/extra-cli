---
task: runAdversarialVerification()
responsavel: "@adversarial-qa-auditor"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: read-only
version: 1.0.0

Entrada:
  - campo: handoff_from_implementer
    tipo: object
    origem: state/handoffs/
    obrigatorio: true
  - campo: execution_card
    tipo: object
    origem: state/execution-cards/
    obrigatorio: true

Saida:
  - campo: verdict
    tipo: string
    destino: state/qa/
    persistido: true
  - campo: findings
    tipo: array
    destino: state/qa/
    persistido: true
  - campo: evidence_bundle
    tipo: object
    destino: state/evidence/
    persistido: true

Checklist:
  - [ ] Diff reviewed
  - [ ] Happy/fail/retry/partial paths considered
  - [ ] False green hunt executed
  - [ ] Claims vs evidence compared
  - [ ] Verdict PASS|FAIL|BLOCKED
  - [ ] Independent from implementer

preconditions:
  - [ ] implementer handoff exists
  - [ ] auditor ≠ implementer session role

postconditions:
  - [ ] verdict persisted
  - [ ] FAIL includes reproducible findings

blockers:
  - none

tools:
  - git
  - pytest
  - make

scripts:


dependencies:
  - delivery-engineer-implement-selected-slice.md

parallelism: no
error_strategy: FAIL_REWORK on FAIL; stop on BLOCKED
retry: 0 (rework loop owned by orchestrator)
persistence: state/qa/
expected_cost: medium-high
---

# *run-adversarial-verification

## Purpose

Destruir hipótese de conclusão; emitir veredito independente.

## Execution Steps

### Step 1 — Review diff against execution card
### Step 2 — Run adversarial checklist
### Step 3 — Execute required tests/commands
### Step 4 — Emit verdict


## Error Handling

```yaml
error: QA_BLOCKED
cause: environment missing for required live proof
resolution: BLOCKED (not PASS)
```


## Acceptance Criteria

  - [ ] Diff reviewed
  - [ ] Happy/fail/retry/partial paths considered
  - [ ] False green hunt executed
  - [ ] Claims vs evidence compared
  - [ ] Verdict PASS|FAIL|BLOCKED
  - [ ] Independent from implementer

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
  - run-adversarial-verification
```

---
*Task runAdversarialVerification() — extra-dod-roi*
