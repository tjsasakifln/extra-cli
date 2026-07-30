# Plan — 900-dod-low-hanging-boundaries-evidence

## Approach

1. Baseline + isolation worktree from `origin/main`  
2. Spec Kit + candidate matrix from controller IDs  
3. `config/scope_boundaries.yaml` + scope auditor + claim guard  
4. Campaign harness `dod_low_hanging_audit` (no accept, no DOD edit)  
5. Adversarial pytest suite  
6. Independent QA shrink set if needed  
7. PR A merge → re-proof → PR B promotions  

## Architecture

```
DOD.md / .dod/manifest.yaml
        │
        ▼
dod_low_hanging_audit (classify SELECTED|REJECTED_*)
        │
        ├── audit_scope_boundaries (per capability proof)
        ├── audit_client_claim_boundaries
        ├── requirement_states / dod_process_integrity (family A)
        ├── dual_capability_coverage (family D)
        └── cli matrix (family C)
        │
        ▼
artifacts/.../proofs/<ITEM_ID>.json  → acceptance-matrix → (PR B) controller accept
```

## Risks

- Numeric target ≥20 must not force false accepts  
- Parallel commercial DOD PR may force PR B draft  
- Governance items without executable enforcement stay open  
