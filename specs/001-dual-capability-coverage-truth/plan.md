# Implementation Plan: Dual Capability Coverage Truth

**Branch**: `campaign/dual-capability-coverage-truth`  
**Date**: 2026-07-21  
**Spec**: `specs/001-dual-capability-coverage-truth/spec.md`

## Summary

Adapt the existing coverage spine into a single dual-capability monitoring-coverage engine. Replace golden-path’s legacy `entity_coverage.is_covered` / `any_row` numerator with independent calculations for `open_tenders` and `historical_contracts`. Reuse `load_canonical_universe`, `coverage_evidence` (+ capability columns from migration 040), `CoverageState` / success_zero rules, and freshness SLAs. Delimit `entity_coverage` as legacy admin/diagnostic only.

## Technical Context

- **Language**: Python 3.12
- **Storage**: PostgreSQL (`coverage_evidence`, optional views; no third parallel table tree)
- **Universe**: `scripts/lib/universe.py`
- **Entry points**: `scripts/coverage/dual_capability_coverage.py`, CLI module, `scripts/golden_path.py`
- **Tests**: pytest unit + optional real_db
- **Target platform**: local golden path / CI

## Constitution Check

| Principle | Status |
|-----------|--------|
| Merge/CI integrity | Preserve tests; no skip-to-green |
| Smallest delta | Adapt spine; no parallel framework |
| Parallel safety | Single owner for golden_path.py, dual engine, DOD/campaign docs |
| Evidence honesty | Errata for 19.5791%; no false 95% |

## Architecture

```
load_canonical_universe()
        │
        ▼
 universe identity stamps (count, seed_sha, ids_sha)
        │
        ├─► applicability partition per capability → A_C
        │
        ├─► load latest coverage_evidence (by entity×source×capability)
        │
        ├─► score each entity in A_C (required sources + success_zero + freshness)
        │
        ├─► data_presence (descriptive, independent)
        │
        └─► dual summary JSON + gap CSV/JSON + ledger fields
```

### Single spine decision

| Reuse | Role |
|-------|------|
| `load_canonical_universe` | Universe authority |
| `coverage_evidence` + mig 040 columns | Evidence ledger |
| `scripts/coverage/states.py` | State machine + success_zero determination helpers |
| `freshness_by_entity` SLAs | 24h / 7d (mapped to dual capability names) |
| `golden_path` ledger | Observability |

| Delimit as legacy | Role after campaign |
|-------------------|---------------------|
| `entity_coverage.is_covered` | Admin/diagnostic only; optional `legacy_metric` stamp |
| `entity_coverage.any_row` | **Forbidden** as coverage method |
| Single aggregated coverage_pct | Superseded by dual blocks |

### Capability name mapping

| Canonical gate name | Freshness/registry alias |
|---------------------|--------------------------|
| `open_tenders` | `notices_or_bids` |
| `historical_contracts` | `contracts` |

### Required source combinations (v1)

| Capability | Required (all must pass) | Complementary (never replace) |
|------------|--------------------------|--------------------------------|
| open_tenders | `pncp` | dom_sc, doe_sc, pcp, compras_gov, … |
| historical_contracts | `pncp` | contracts, tce_sc, … |

## Data Model

No mandatory new tables if `coverage_evidence.capability` is populated. Optional migration `058_dual_capability_coverage_views.sql`:

- View `v_dual_capability_coverage_latest` — latest evidence per (entity_id, source, capability)
- Comments delimiting `entity_coverage` as non-canonical for gates

Backfill: not required for measurement correctness; empty evidence → 0% covered with measurement_success.

## Compatibility

- Existing `--execute-coverage-only` becomes dual-capable (details include both capabilities).
- New `--execute-dual-coverage-only` + `--capability {open_tenders,historical_contracts,both}`.
- Legacy single `numerator`/`coverage_pct` fields retained only as non-canonical mirrors of open_tenders for transition, with `method=dual_capability_coverage` and explicit `legacy_forbidden_methods`.

## Risks & Rollback

| Risk | Mitigation |
|------|------------|
| Low live % after correct math | Expected; document honestly |
| Evidence lacks capability column | Map data_type bids→open_tenders, contracts→historical_contracts |
| DB entity_id int vs seed entity_id str | Join via cnpj8 / identity_key; fail closed if gate requires unresolved identity |
| Tests assuming any_row | Update to dual contract |

**Rollback**: revert golden_path to previous function; dual module is additive.

## Test Plan

1. Unit: pure scoring, success_zero validators, fail-closed identity, no average, no any_row.
2. Integration: migrations zero + reapply; dual report on test DB.
3. CLI: help flags; dual-only mode; exit codes.
4. Claims scan: 19.5791 only in errata/historical.
5. Quality: ruff on touched files; pytest selective.

## Implementation Phases

1. Spec Kit artifacts + ADR-030  
2. `dual_capability_coverage.py` + CLI  
3. golden_path integration  
4. migration views (optional)  
5. tests + quality  
6. errata + campaign docs + DOD honesty  
7. analyze/converge + PR  
