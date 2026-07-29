# Coverage Truth Verdict — DUAL-CAPABILITY-SUSTAINED-COVERAGE-95-01-PARALLEL

**Audited at:** 2026-07-29T12:27:55.440874+00:00  
**Baseline SHA (origin/main):** `d05d4c3de152b562493715f114e0a387fcb63dc3`  
**Universe:** 1093 entities — version `d65f272812cf:0b3f894d87ba:1093` (matches prior claims)

## Executive conclusion

| Claim | Dual-joint legitimate? | Notes |
|-------|------------------------|-------|
| open_tenders 1093/1093 (100%) | **NO** | Aggregate only; 1092 SUCCESS_ZERO; data_presence 0%; no entity ledger; SHA ≠ baseline/contracts |
| historical_contracts 1093/1093 (100%) | **NO** as dual | Single-capability; `scope_complete=false`; `dual_gate_status=NOT_EVALUATED`; policy 2.1.0 ≠ current 2.1.1 |
| Manual join of both 100% | **FORBIDDEN** | Different SHAs, as_of, policy; contract requires one campaign invocation |
| Prior joint dual reproofs | **FAIL / NOT_READY** | Documented dual_gate FAIL |

## open_tenders SUCCESS_ZERO mass

- Declared: **1092** SUCCESS_ZERO, **1** SUCCESS_WITH_DATA, data_presence_pct=**0**
- Stratified sample size: **54** (≥ max(50, 5% of 1092))
- Classifications: **all UNSUPPORTED** (no per-entity raw/hash/pages/query in committed artifacts)
- **CONFIRMED_ZERO count: 0**
- Recalculated floor coverage: **1/1093 ≈ 0.09%** → gate **FAIL**

## historical_contracts

- Stronger presence signal (412 with data, 37.3% presence) but **not** dual-complete
- dual-summary: scope_complete=false, pipeline_success=false, dual_gate=NOT_EVALUATED

## Dual gate eligibility from historical evidence

```
scope_complete = false (prior single-cap runs) | true but FAIL (reproofs)
pipeline_success = false
dual_gate_status ∈ {NOT_EVALUATED, FAIL, NOT_READY}
```

**No existing repository artifact proves joint dual ≥95% PASS under current contract.**

## Current active policy

- version: **2.1.1** (active)
- file sha256: `9a9e8f8687bd965ee0a1f797321fc098a8a8c208ff1f05c5b786e12e9af1246c`
- prior HC run used **2.1.0** / sha `f090ff87dbd2d073fb5c7ca89d42bda690deffb7656e6bde8fa2c01446b492e2`

## Next measurement requirement

One invocation:

```bash
python3 -m scripts.coverage.dual_capability_coverage \
  --capability both --dsn "$ISOLATED_OR_PROD_RO_DSN" \
  --seed fixtures/canonical_universe_r0.xlsx \
  --output-dir "$OUTPUT_DIR/local-dual" --require-gate
```

Must emit dual summary with both capabilities, matching code_sha/policy/universe/as_of, entity ledger, and validated SUCCESS_ZERO only.
