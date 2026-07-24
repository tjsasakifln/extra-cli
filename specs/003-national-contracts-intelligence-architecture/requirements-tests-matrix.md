# Requirements × Tests Matrix (PR #121 close)

| Requirement | Evidence |
|-------------|---------|
| FR-001 scope labels | contracts/scope-classification.md; product envelope scope_label |
| FR-002 provenance | lineage.py fields |
| FR-003 SC coverage independence | test_adversarial_nv_matrix NV-01..08; test_coverage_isolation_*; dual suite |
| FR-004 no second backfill | non-goals; safety proofs |
| FR-005 competitors | test_products_fixture competitors; CLI |
| FR-006 benchmarks | test_benchmarks_sample_gate |
| FR-007 agencies | test_agencies_profiles |
| FR-008 hypothesis labels | entrant_signal claim_class |
| FR-009 catalog | products/product-catalog.md |
| FR-010 interface | contract_intel national-* facade + national_intel CLI; ADR-entry-point |
| FR-011 layers | ADR-national-intel-layers |
| FR-012 additive schema | migration 059 |
| FR-013 isolation | safety/*; conftest NATIONAL_INTEL_DSN; refuse 5433 default |
| FR-014 adversarial | NV matrix P0 |
| FR-015 lineage | product JSON examples |
| FR-016 reuse | facade + matrix; deliverables not forked |

## Counts (local close)

- `tests/national_intel/` + `tests/test_dual_capability_coverage.py` = **65 passed**
