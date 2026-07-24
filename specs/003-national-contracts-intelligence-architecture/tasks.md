# Tasks: National Contracts Intelligence Architecture

**Input**: plan.md, spec.md, research.md, data-model.md, contracts/  
**Campaign**: NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01

## Phase 1: Setup

- [x] T001 Campaign safety isolation artifacts under `artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/safety/`
- [x] T002 Independent worktree + branch from `origin/main` + isolated DB 5435
- [x] T003 Spec Kit skeleton `specs/003-national-contracts-intelligence-architecture/` (spec, checklist, contracts)
- [x] T004 [P] Inventory A/C/D/E artifacts written

## Phase 2: Foundational

- [x] T005 plan.md + research.md + data-model.md + quickstart.md
- [x] T006 ADR layer separation in `artifacts/.../architecture/ADR-national-intel-layers.md`
- [x] T007 Migration `db/migrations/059_national_contracts_intelligence_layers.sql` (views only)
- [x] T008 Package scaffold `scripts/national_intel/` (`__init__.py`, `lineage.py`, `cli.py`)
- [x] T009 Apply migrations on isolated DSN only; record proof in `artifacts/.../migrations/`
- [x] T010 Fixture helper / conftest for isolated Postgres + sample contracts

**Checkpoint**: Foundation ready for US implementation

## Phase 3: US1 — National vs SC coverage isolation (P1) 🎯

**Goal**: Prove national volume cannot inflate SC operational coverage

- [x] T011 [US1] Unit/integration tests in `tests/national_intel/test_coverage_isolation_national_volume.py`
- [x] T012 [US1] Document invariants copy in coverage-isolation linked from tests
- [x] T013 [US1] Ensure dual coverage path not modified; tests import existing engine or pure invariants

## Phase 4: US2 — Competitors geo (P1)

- [x] T014 [US2] `scripts/national_intel/competitors.py` rankings + UF footprint
- [x] T015 [US2] CLI subcommand `competitors`
- [x] T016 [US2] Example artifact under `products/competitors/`
- [x] T017 [US2] Fixture tests for multi-UF supplier

## Phase 5: US3 — Benchmarks (P1)

- [x] T018 [US3] `scripts/national_intel/benchmarks.py` with min_sample gate
- [x] T019 [US3] CLI subcommand `benchmarks`
- [x] T020 [US3] Example artifact under `products/benchmarks/`
- [x] T021 [US3] Tests insufficient_sample + happy path

## Phase 6: US4 — Agencies (P2)

- [x] T022 [US4] `scripts/national_intel/agencies.py`
- [x] T023 [US4] CLI subcommand `agencies`
- [x] T024 [US4] Example artifact under `products/agencies/`
- [x] T025 [US4] Fixture tests

## Phase 7: US5/US6 — Delivery + isolation polish

- [x] T026 [US5] CLI main + `--help` docs; quickstart validation
- [x] T027 [US6] STATUS.md gates update; protected path smoke (no HC write)
- [x] T028 Product catalog already in products/; ensure 3 products linked

## Phase 8: Quality & review

- [x] T029 [P] pytest `tests/national_intel/` green on 5435
- [x] T030 Independent review notes `artifacts/.../review/independent-review.md`
- [x] T031 SUMMARY.md final report
- [x] T032 analyze-report.md Spec Kit consistency
- [x] T033 Local commits (no force push; no merge)

## Dependency graph

```text
T001-T005 done
T006-T010 foundational
T011-T013 US1 || T014-T017 US2 || T018-T021 US3  (after T010)
T022-T025 after T010
T026-T033 after products+tests
```

## Parallel examples

```text
Wave impl: T007 (SQL) | T008 (scaffold) 
Then: T011 | T014 | T018 | T022
Then: T029 review
```
