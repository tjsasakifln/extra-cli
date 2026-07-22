# Tasks: Dual Capability Coverage Truth

**Input**: `spec.md`, `plan.md`  
**Tests**: adversarial + mutation probes  
**Updated**: 2026-07-22 completion mission

## Phase 1 — Setup

- [x] T001 Create Spec Kit feature dir `specs/001-dual-capability-coverage-truth/`
- [x] T002 Record campaign baseline under `docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/`
- [x] T002b Write `completion-baseline.md` (PR#108/107/main/CI)

## Phase 2 — Foundational

- [x] T003 Write ADR-030 (`docs/architecture/adr/ADR-030-dual-capability-coverage-truth.md`)
- [x] T004 Write errata ERRATA-19-5791.md
- [x] T005 Migration `db/migrations/058_dual_capability_coverage_views.sql`

## Phase 3 — Dual engine (P1)

- [x] T006 Implement `scripts/coverage/dual_capability_coverage.py` v1.0 spine
- [x] T007 success_zero + freshness validators
- [x] T008 Unit tests initial matrix
- [x] T009 CLI module entrypoint
- [x] T021 **Fail-closed DB load** — classify schema/query/permission/connection; legacy only when modern columns proven absent; record `schema_compatibility_mode`  
  Files: `scripts/coverage/dual_capability_coverage.py`
- [x] T022 **Mapping integrity** — metrics `db_entities_*`, no CNPJ first-wins; ambiguous roots identity_unresolved  
  Files: `scripts/coverage/dual_capability_coverage.py`
- [x] T023 **Presence status enum** — fail closed on query/column errors; real schema `matched_entity_id`/`orgao_cnpj`  
  Files: `scripts/coverage/dual_capability_coverage.py`
- [x] T024 **Applicability matrix integrated** — `build_applicability_resolutions` + fold; default unknown without proven rule  
  Files: `scripts/coverage/dual_capability_coverage.py`, `scripts/coverage/applicability_matrix.py` (reuse)
- [x] T025 **Set integrity** — outsider in obs/presence → `entity_id_outside_canonical_universe`; result set == universe  
  Files: `scripts/coverage/dual_capability_coverage.py`, `tests/test_dual_capability_coverage.py`
- [x] T026 **Hash validation** — expected_seed/ids/count/universe_version  
  Files: dual engine + CLI
- [x] T027 **success_with_data rigor** — persist>0, timestamps, provenance, pagination  
  Files: dual engine + tests
- [x] T028 **success_zero rigor** — error_message tokens; reject bare supports_zero_proof  
  Files: dual engine + tests
- [x] T029 **Aggregates + reconciliation** — pending/never/error/unknown published; partition checks  
  Files: dual engine + tests
- [x] T030 **Remove vacuous tests** — delete `or True`; true dual denominators 3 vs 2  
  Files: `tests/test_dual_capability_coverage.py`

## Phase 4 — Golden path

- [x] T010 Replace `run_coverage_calculation` with dual engine
- [x] T011 `--execute-dual-coverage-only` + `--capability`
- [x] T012 Update `tests/test_golden_path_coverage.py`
- [x] T031 Forward planilha seed path + hashes into coverage step  
  Files: `scripts/golden_path.py`

## Phase 5 — Reports & claims

- [x] T013 Summary JSON + gap CSV/JSON
- [x] T014 Claims scan artifacts
- [x] T015 DOD PARTIAL dual measurement annotation
- [x] T016 NEXT-DOD-PATH.md

## Phase 6 — Spec Kit honesty

- [x] T017 Re-analyze findings (FR-016..024)
- [x] T018 Checklist `checklists/requirements.md`
- [x] T019 ruff + pytest selective
- [x] T020 PR push + CI green on final SHA
- [x] T032 Independent review PASS_FOR_MERGE
- [x] T033 Merge PR to main
- [x] T034 Main reproof (migrations + dual CLI + golden path)
- [x] T035 Acceptance pack + controller (no self-QA)
- [x] T036 Normative DOD ACCEPTED only after controller

## Dependencies

```
T001→T002→T003/T004→T006→T021…T030
T006→T010→T031→T011→T012
T019→T020→T032→T033→T034→T035→T036
```

## Closed process tasks (evidence)

* T020: PR #108 CI green + merge `edd7618`
* T032: independent reviews v1.1/v1.2/v1.3
* T033: PR #108 merged
* T034: main dual reproof after merges
* T035: `dod_controller accept` + pack `DOD-rol-1-definition-of-done-4efe05fc94`
* T036: PR #109 DOD ACCEPTED dual calcula cobertura
* T040–T044: skeptic remediation #110/#111 + cap-level honesty

## Remaining operational (not engine implementable)

* identity_unresolved CNPJ roots → 0
* coverage_evidence backfill → dual 95%

## Phase 7 — Skeptic remediation (post-accept)

- [x] T040 Single-capability: scope_complete=false, dual_gate_status=NOT_EVALUATED, pipeline_success=false  
  Files: `scripts/coverage/dual_capability_coverage.py`, `scripts/golden_path.py`, tests
- [x] T041 identity_unresolved → measurement_success=false; mapping_status preserved  
  Files: `scripts/coverage/dual_capability_coverage.py`, tests
- [x] T042 Use `v_dual_capability_evidence_latest` in evidence load (not dead view)  
  Files: `scripts/coverage/dual_capability_coverage.py`, migration 058
- [x] T043 Update tasks/STATUS after merge/accept honesty  
  Files: `specs/.../tasks.md`, campaign STATUS
- [x] T044 Independent review with executed attacks + commands on fix SHA  
  Files: campaign independent-review artifact
