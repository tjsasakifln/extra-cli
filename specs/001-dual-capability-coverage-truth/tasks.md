# Tasks: Dual Capability Coverage Truth

**Input**: `spec.md`, `plan.md`  
**Tests**: included (campaign requires failing the old model)

## Phase 1 — Setup

- [x] T001 Create Spec Kit feature dir `specs/001-dual-capability-coverage-truth/` with constitution-aligned artifacts
- [x] T002 Record campaign baseline under `docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/baseline.md`

## Phase 2 — Foundational

- [x] T003 [P] Write ADR-030 single spine decision (`docs/architecture/adr/ADR-030-dual-capability-coverage-truth.md`)
- [x] T004 [P] Write errata for legacy 214/1093 (`docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/ERRATA-19-5791.md`)
- [ ] T005 Optional migration `db/migrations/058_dual_capability_coverage_views.sql` (views + entity_coverage delimitation comments)

## Phase 3 — User Story 1+2 (P1) Dual engine

- [x] T006 [US1] Implement `scripts/coverage/dual_capability_coverage.py` (universe identity, dual formulas, presence, gaps, fail-closed)
- [x] T007 [US1] Implement success_zero + freshness validators per FR-005/006
- [x] T008 [US2] Unit tests `tests/test_dual_capability_coverage.py` covering adversarial matrix
- [x] T009 [US1] CLI `python -m scripts.coverage.dual_capability_coverage`

## Phase 4 — User Story 4 (P1) Golden path

- [x] T010 [US4] Replace `run_coverage_calculation` to call dual engine; ban any_row method
- [x] T011 [US4] Add `--execute-dual-coverage-only` and `--capability`
- [x] T012 [US4] Update `tests/test_golden_path_coverage.py` for dual contract

## Phase 5 — User Story 3 (P2) Reports & claims

- [x] T013 [US3] Write summary JSON + nominal gap CSV/JSON under `output/coverage/`
- [x] T014 Claims scan + document results in campaign dir
- [x] T015 Honest DOD annotation for §12.1 calcula cobertura → PARTIAL dual measurement
- [x] T016 `NEXT-DOD-PATH.md`

## Phase 6 — Polish

- [x] T017 Speckit analyze report (no untreated CRITICAL/HIGH)
- [x] T018 Speckit converge checklist
- [x] T019 ruff + pytest selective + capture evidence in scratch
- [ ] T020 PR + CI (requires remote); reproof commands documented if merge blocked

## Dependencies

```
T001 → T002 → T003/T004 → T006 → T007 → T008 → T009
T006 → T010 → T011 → T012
T006 → T013 → T014 → T015 → T016
T008+T012 → T017 → T018 → T019 → T020
```

## Parallel opportunities

- T003 ∥ T004  
- T008 ∥ T009 after T006  
- T013 ∥ T014 after engine stable  
