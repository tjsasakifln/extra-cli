# Requirements checklist — dual capability coverage truth

**Feature:** `001-dual-capability-coverage-truth`  
**Updated:** 2026-07-22 (final-closure mission)

| ID | Requirement | Verifiable scenario | Status |
|----|-------------|---------------------|--------|
| FR-001 | Dual independent coverage metrics | `test_different_denominators_per_capability` | DONE |
| FR-002 | Universe from seed + hash stamps | `test_compute_validates_expected_hashes` | DONE |
| FR-003 | Denominator A_C after applicability | matrix fold + unknown not in den | DONE |
| FR-004 | Numerator requires validated success+fresh | observation_counts_as_covered | DONE |
| FR-005 | Freshness SLAs | stale not in numerator | DONE |
| FR-006 | success_zero validators | error_message / pagination tests | DONE |
| FR-007 | data_presence separate + fail-closed | `test_presence_fail_closed` | DONE |
| FR-008 | No any_row / is_covered | FORBIDDEN_METHODS | DONE |
| FR-009 | No average | dual denominators test | DONE |
| FR-010 | Golden path dual mode | CLI + exit semantics | DONE |
| FR-011 | Fail-closed integrity | outsider/hash tests | DONE |
| FR-012 | Structured reports | `test_write_reports` | DONE |
| FR-013 | measurement vs gate vs pipeline | exit semantics | DONE |
| FR-014 | Legacy 19.5791% errata | ERRATA-19-5791.md | DONE |
| FR-015 | Honest DOD (no false 95%) | method vs live separation | DONE |
| FR-016 | Fail-closed schema/query | classified exceptions | DONE |
| FR-017 | Multi-key identity no first-wins | `test_identity_multikey_resolution` | DONE |
| FR-018 | Presence status enum + null pct | `test_presence_fail_closed` | DONE |
| FR-019 | Applicability matrix/policy live | `build_applicability_resolutions` + source_policy | DONE |
| FR-020 | Hash validation expected_* | dual tests | DONE |
| FR-021 | success_with_data requires persist | unit tests | DONE |
| FR-022 | Publish pending/never aggregates | unit tests | DONE |
| FR-023 | Reconciliation math | unit tests | DONE |
| FR-024 | No vacuous tests | dual suite | DONE |
| FR-025 | Single required_combinations authority | `test_source_policy_canonical` | DONE |
| FR-026 | Draft/missing policy → NOT_READY | `test_compute_dual_rejects_missing_policy` | DONE |
| FR-027 | Active policy metadata + hash | `test_active_policy_loads_with_verified_hash` | DONE |
| FR-028 | No hardcoded esfera | `derive_esfera` / unknown when absent | DONE |
| FR-029 | Combination semantics | municipal pncp+ciga; complementary no replace | DONE |
| FR-030 | Combination audit fields | combination_audit_sample in report | DONE |
| FR-031 | Acceptance method vs live | pack 1fdea0f6e6 + SUPERSEDED 4efe05fc94 | DONE |
| FR-032 | SHA roles not “current tip” | campaign stamps | DONE |

## Closure checklist

| Item | Status |
|------|--------|
| Implementation branch | `fix/dual-canonical-closure` |
| Live identity_unresolved_count | 0 |
| Policy status active | YES v2.0.0 |
| Independent review on final SHA | PENDING until PR tip |
| CI green | PENDING until push |
| PR #107 resolution | PENDING |
| Normative DOD re-accept | pack created; controller on merge |
