---
task: publishEvidenceAndHandoff()
responsavel: "@evidence-release-steward"
responsavel_type: agent
atomic_layer: task
elicit: false
mode: write
version: 1.0.0

Entrada:
  - campo: qa_verdict
    tipo: string
    origem: state/qa/
    obrigatorio: true
    validacao: "must be PASS for DoD edits"
  - campo: write_permission
    tipo: boolean
    origem: User Input
    obrigatorio: true

Saida:
  - campo: evidence_pack
    tipo: object
    destino: state/evidence/
    persistido: true
  - campo: draft_pr_url
    tipo: string
    destino: Return
    persistido: true
  - campo: cycle_report
    tipo: object
    destino: state/cycles/
    persistido: true
  - campo: dod_updated
    tipo: boolean
    destino: Return
    persistido: true

Checklist:
  - [ ] Evidence commands and exit codes recorded
  - [ ] DoD updated only if PASS + authorized claims
  - [ ] Draft PR opened (not merged)
  - [ ] Forbidden claims documented
  - [ ] Residual risks listed
  - [ ] Cycle report written

preconditions:
  - [ ] QA PASS for claimful DoD updates
  - [ ] write_permission

postconditions:
  - [ ] no merge performed
  - [ ] report complete

blockers:
  - none

tools:
  - git
  - gh

scripts:


dependencies:
  - adversarial-qa-auditor-run-adversarial-verification.md

parallelism: no
error_strategy: never merge; partial publish of evidence ok
retry: 1 for gh flakiness
persistence: state/evidence/ + state/cycles/
expected_cost: medium
---

# *publish-evidence-and-handoff

## Purpose

Consolidar evidências, atualizar docs/DoD só com autorização de prova, abrir draft PR, sem merge.

## Execution Steps

### Step 1 — Package evidence
### Step 2 — Conditional DoD/docs update
### Step 3 — Final atomic commits if needed
### Step 4 — Open draft PR via gh
### Step 5 — Cycle report + next ROI pointer


## Error Handling

```yaml
error: PUBLISH_DENIED
cause: QA not PASS
resolution: skip DoD; keep evidence only
```


## Acceptance Criteria

  - [ ] Evidence commands and exit codes recorded
  - [ ] DoD updated only if PASS + authorized claims
  - [ ] Draft PR opened (not merged)
  - [ ] Forbidden claims documented
  - [ ] Residual risks listed
  - [ ] Cycle report written

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
  - publish-evidence-and-handoff
```

---
*Task publishEvidenceAndHandoff() — extra-dod-roi*
