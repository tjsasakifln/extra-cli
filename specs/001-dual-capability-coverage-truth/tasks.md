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

## Phase 7 — Final closure (canonical policy + identity)

- [x] T040 Single source_policy authority + required_combinations
- [x] T041 Activate policy with verified hash (v2.0.0)
- [x] T042 Remove hardcoded esfera; unknown when absent
- [x] T043 Presence fail-closed (null pct)
- [x] T044 Multi-key identity resolution (00394494)
- [x] T045 Supersede pack 4efe05fc94; create 1fdea0f6e6
- [x] T046 Spec/checklist/analyze refresh FR-025..032
- [x] T047 Implementation PR #115 + CI green
- [x] T048 Independent review v1.4 PASS_FOR_MERGE (`c06d7cd`, ancestor of main)
- [x] T049 Resolve PR #107 (rebase → mergeable=true → MERGED `a7b213e`)
- [x] T050 Main merge reproof + converge (`a7b213e` / docs `dbc9065`)

## Dependencies

```
T001→T002→T003/T004→T006→T021…T030
T006→T010→T031→T011→T012
T019→T020→T032→T033→T034→T035→T036
T040…T046→T047→T048→T049→T050
```

## Closed process tasks (evidence)

* T020: PR #108 CI green + merge `edd7618`
* T032: independent reviews v1.1/v1.2/v1.3
* T033: PR #108 merged
* T034: main dual reproof after merges
* T035: `dod_controller accept` + pack `DOD-rol-1-definition-of-done-4efe05fc94`
* T036: PR #109 DOD ACCEPTED dual calcula cobertura
* T040–T044: skeptic remediation #110/#111 + cap-level honesty

## Remaining operational (not engine implementable this mission)

* coverage_evidence backfill → dual 95% candidacy (explicitly out of measurement-truth scope)
* 147 entities with unknown esfera (consórcios/SEM) — honest unknown, no invention

## Phase 7 — Skeptic remediation (historical #110–#112)

- [x] T040 Single-capability scope honesty
- [x] T041 identity_unresolved → measurement_success=false
- [x] T042 dual evidence view
- [x] T043 STATUS honesty
- [x] T044 Independent review v1.3

## Phase 8 — Final canonical closure

- [x] T050 Single source_policy authority + required_combinations (v2.0.0 active, hash verified)
- [x] T051 No silent DEFAULT_REQUIRED_SOURCES (allow_fallback=False returns empty)
- [x] T052 MANDATORY_SOURCES = full MIN combination (not first-source-only)
- [x] T053 Multi-key identity; live identity_unresolved_count=0
- [x] T054 Presence fail-closed + real PG tests
- [x] T055 Pack 4efe SUPERSEDED; pack 1fdea0f6e6 with verify/proof
- [x] T056 PR #115/#107/#116/#117 merged; PR #107 was mergeable=true
- [x] T057 Independent review v1.5 + re-review on final main tip after skeptic-final PR
- [x] T058 Controller re-accept without CI/review/divergence gate bypasses on main tip
- [x] T059 Spec Kit tasks/checklist/analyze/converge aligned to final main
- [x] T060 No DEFAULT_REQUIRED_SOURCES residual in build_applicability_resolutions
- [x] T061 Presence PG tests drive load_data_presence (table_absent via rename)
