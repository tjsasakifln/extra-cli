# ADR-029 — Dual capability coverage truth (single spine)

**Status:** Accepted  
**Date:** 2026-07-21  
**Campaign:** `DUAL-CAPABILITY-COVERAGE-TRUTH-01`  
**Spec:** `specs/001-dual-capability-coverage-truth/`

## Problem

Operational “coverage” was ambiguous. Golden path `run_coverage_calculation` counted
`entity_coverage.is_covered` and fell back to `entity_coverage.any_row`, producing a single
percentage (historically cited as 214/1093 = 19.5791%) without:

* capability split (`open_tenders` vs `historical_contracts`);
* set equality to the planilha universe;
* freshness in the numerator;
* validated `success_zero`;
* separation from data presence.

That metric cannot gate DOD dual 95% requirements.

## Alternatives evaluated

1. **Keep entity_coverage as authority** — Rejected: admin rows ≠ monitoring coverage.
2. **New parallel table tree** — Rejected: third architecture when `coverage_evidence` + universe already exist.
3. **Adapt dual spine on coverage_evidence + load_canonical_universe** — **Selected**.

## Structures reused

* `scripts/lib/universe.load_canonical_universe` — universe authority
* `coverage_evidence` (+ migration 040 capability/applicability/freshness columns)
* `scripts/coverage/states.py` — state machine vocabulary
* Freshness SLAs (24h editais / 7d contracts incremental) aligned with ADR-028
* Golden path ledger + StepRecord

## Structures declared legacy / non-canonical

* `entity_coverage.is_covered` — diagnostic/admin only
* `entity_coverage.any_row` — **forbidden** as coverage method
* Single undifferentiated `coverage_pct` without capability — superseded
* Historical claim **214/1093 = 19.5791%** — see campaign errata

## Decision

Canonical module: `scripts/coverage/dual_capability_coverage.py`.

```
capability_monitoring_coverage(C) =
  |{ e ∈ A_C : required sources complete, validated success, fresh, no blocker }|
  / |A_C|
```

Computed independently for `C ∈ {open_tenders, historical_contracts}`.

Presence, freshness counts, applicability, and blockers are reported separately.

## Invariants

1. Universe from seed only; stamp count + seed_sha256 + ordered ids sha256.
2. No average / cross-capability compensation.
3. No any_row / undifferentiated is_covered as method.
4. stale/unknown/partial never enter numerator.
5. success_zero requires pagination/completion proof + run identity.
6. Fail closed on set integrity violations.
7. measurement_success ≠ coverage_gate_pass ≠ pipeline_success.

## Compatibility

* `--execute-coverage-only` uses dual engine.
* `--execute-dual-coverage-only` + `--capability` for isolated reproof.
* Legacy metric stamped under `legacy_metric` only (non-canonical).

## Migration

Optional `058_dual_capability_coverage_views.sql` documents views/comments.
No destructive change to `entity_coverage`.

## Backfill

Not required for measurement correctness. Empty evidence ⇒ 0% covered, measurement_success true.

## Rollback

Revert `golden_path.run_coverage_calculation`; dual module is additive.

## Risks

* Live % will look “worse” after correct math — expected honesty.
* DB entity_id mapping via cnpj8 may leave some evidence unmapped (fail-closed: not counted, not silently inflated).

## Consequences

* DOD §12.1 “calcula cobertura” becomes dual measurement (PARTIAL until live dual evidence pack registered via acceptance controller).
* Dual 95% gates remain open until operational backfill/freshness proves them.
