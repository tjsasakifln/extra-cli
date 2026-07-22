# Requirements checklist — dual capability coverage truth

**Feature:** `001-dual-capability-coverage-truth`  
**Updated:** 2026-07-22 (completion mission)

| ID | Requirement | Verifiable scenario | Status |
|----|-------------|---------------------|--------|
| FR-001 | Dual independent coverage metrics | `test_different_denominators_per_capability`, `test_tenders_do_not_prove_contracts` | DONE |
| FR-002 | Universe from seed + hash stamps | `build_universe_identity`, `test_compute_validates_expected_hashes` | DONE |
| FR-003 | Denominator A_C after applicability | matrix fold + `test_unknown_applicability_not_in_denominator` | DONE |
| FR-004 | Numerator requires validated success+fresh | `observation_counts_as_covered` tests | DONE |
| FR-005 | Freshness SLAs | `test_stale_not_in_numerator`, `test_mutation_freshness_removed_fails_cover` | DONE |
| FR-006 | success_zero validators | `test_success_zero_rejects_error_message_only`, pagination tests | DONE |
| FR-007 | data_presence separate | presence fields + claims_forbidden | DONE |
| FR-008 | No any_row / is_covered | FORBIDDEN_METHODS + golden path method | DONE |
| FR-009 | No average | summary keys + dual denominators test | DONE |
| FR-010 | Golden path dual mode | CLI flags + exit 2 on gate fail | DONE |
| FR-011 | Fail-closed integrity | outsider/hash/den tests | DONE |
| FR-012 | Structured reports | `test_write_reports` | DONE |
| FR-013 | measurement vs gate vs pipeline | exit semantics tests | DONE |
| FR-014 | Legacy 19.5791% errata | ERRATA-19-5791.md | DONE |
| FR-015 | Honest DOD (no false 95%) | DOD PARTIAL annotation | DONE |
| FR-016 | Fail-closed schema/query (no empty swallow) | classified exceptions; no bare except→zero | DONE |
| FR-017 | Mapping metrics + no first-wins CNPJ | EntityMappingMetrics; ambiguous roots excluded | DONE |
| FR-018 | Presence status enum | table_absent/query_failed/column_absent/no_rows/rows_present/unmapped_rows | DONE |
| FR-019 | Applicability matrix consulted by engine | `build_applicability_resolutions` + fold | DONE |
| FR-020 | Hash validation expected_* | CLI + golden path planilha handoff | DONE |
| FR-021 | success_with_data requires persist | `test_success_with_data_requires_persist` | DONE |
| FR-022 | Publish pending/never/error aggregates | `test_pending_and_never_published_not_unknown_zero` | DONE |
| FR-023 | Reconciliation math | applicable partition + applicable buckets | DONE |
| FR-024 | No vacuous tests (`or True`) | removed; denominators truly distinct | DONE |

## Acceptance / merge (not code-complete until done)

| Item | Status |
|------|--------|
| PR merge to main | OPEN |
| CI green on final SHA | OPEN (re-run after push) |
| Independent review PASS_FOR_MERGE | OPEN |
| Acceptance pack + controller | OPEN |
| Main reproof | OPEN |
| Normative DOD ACCEPTED | OPEN (code-ready only) |
