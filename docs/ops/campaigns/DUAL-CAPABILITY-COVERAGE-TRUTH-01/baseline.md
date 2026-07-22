# Baseline — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Recorded:** 2026-07-22T01:14:59.615788Z  
**Branch:** campaign/dual-capability-coverage-truth  
**Base main:** 5a19df7dcd938af255ab5f44dc8d4d2137da40b2

## Concurrent work (do not clobber)

- PR #107 valores report (OPEN)
- PR #63 weekly-strict-fail-closed / entity freshness (DRAFT)
- PR #66 full-suite green (DRAFT)
- ENTITY-FRESHNESS-01 campaign (freshness dual — complementary, not dual monitoring coverage)
- Multiple continue-0x accept branches

## Pre-change golden path coverage method

```
entity_coverage.is_covered → fallback entity_coverage.any_row
den=load_canonical_universe().included
num=count(distinct entity_id) without capability split
```

Historical sealed claim on DOD §12.1: den=1093 num=214 pct=19.5791 (PR #83 evidence pack).

## Goal of campaign

Replace method with dual_capability_coverage; errata 19.5791%; honest dual gates.
