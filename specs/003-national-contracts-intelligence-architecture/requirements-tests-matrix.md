# Requirements × Tests Matrix

**Feature:** 003-national-contracts-intelligence-architecture  
**As of:** 2026-07-22

| Requirement | Test / evidence | Path |
|-------------|-----------------|------|
| FR-001 scope classification | scope labels contract + views `v_intel_*` | `contracts/scope-classification.md`, migration 059, `test_views_exist` |
| FR-002 provenance | product envelope lineage fields | `lineage.py`, product example JSON |
| FR-003 SC coverage independence | NV-01..08, UQ-*, before/after dual | `test_adversarial_nv_matrix.py`, `test_coverage_isolation_national_volume.py` |
| FR-004 no second backfill | non-goal + no crawl invocation in suite | safety + STATUS non-claims |
| FR-005 competitors | CLI + fixture test multi-UF | `test_competitors_multi_uf_*`, products/competitors/example.json |
| FR-006 benchmarks | sample gate tests | `test_benchmarks_sample_gate` |
| FR-007 agencies | agency profile test | `test_agencies_profiles` |
| FR-008 partners hypothesis only | entrant_signal claim_class=hypothesis | competitors product test |
| FR-009 product catalog ≥9 | product-catalog.md | artifacts/.../products/product-catalog.md |
| FR-010 interface | `python -m scripts.national_intel` | cli + quickstart |
| FR-011 layering | ADR + research | architecture/ADR-*, research.md |
| FR-012 additive schema | migration 059 CREATE VIEW only | db/migrations/059_*.sql |
| FR-013 isolation | safety artifacts + conftest refuse 5433 | safety/*, conftest.py |
| FR-014 adversarial coverage | full NV matrix P0 | test_adversarial_nv_matrix.py |
| FR-015 lineage outputs | envelope required keys | product JSON examples |
| FR-016 reuse deliverables | catalog reuse doc | products/reuse-existing-deliverables.md |
| SC-001 distinguish metrics | dual limitations + product scope_label | dual tests + products |
| SC-002 adversarial pass | 26 pytest national_intel | artifacts/tests/pytest-national-intel.log |
| SC-003 three products | competitors/benchmarks/agencies | products/*/example.json |
| SC-005 isolation gate | safety/* | PARALLEL_ISOLATION_PASS |
| SC-006 no DOD mark | STATUS non-claims | STATUS.md |

## Dual spine path under test

All coverage isolation tests call **`compute_dual_coverage`** from `scripts.coverage.dual_capability_coverage` and/or **`load_canonical_universe`** from `scripts.lib.universe`. No reimplemented calculator.
