# CTO Findings — EXTRA-PRS-186-187-TRUST-HARDENING-01

## Executive summary
Both PRs were **honestly not merge-ready** at campaign start despite green CI on #186 and mostly green #187 (ruff fail). Trust gaps were real: decorative brand, mutation-on-GET reviews, silent 404, declarative-only pSEO allowlists, non-atomic export, `fetchall`, and documentary human gates.

After hardening, both PRs are **materially safer** but remain **PARTIAL_BLOCKED** for merge until residual evidence gaps close.

## Decision framework applied
1. Security / no false claims  
2. Behavior proven by tests  
3. Existing contracts  
4. Official brand from web-cfg  
5. PR docs  
6. Implementation convenience  

## Merge recommendation
- **Do not merge** either PR as PASS_MERGE_READY today.
- **#186**: Acceptable for continued review after CI re-run; fix residual workbench e2e flake if red in CI.
- **#187**: Acceptable for continued review; require human approval path demos and consumer contract before any “publish ready” language.

## What would flip to PASS_MERGE_READY
### #186
- Full `npm run test:e2e` green in CI (including workbench PDF)
- Optional: documented REAL preflight READY proof in RO env (or keep PARTIAL live claim)

### #187
- Measured chunked export on ≥250k synthetic rows (time + peak memory log)
- web-cfg consumer contract test green (or explicit CONSUMER_INTEGRATION_NOT_PROVEN accepted by product)
- Sample approval artifact round-trip to PUBLISH_READY on a fixture hash (still no deploy)
