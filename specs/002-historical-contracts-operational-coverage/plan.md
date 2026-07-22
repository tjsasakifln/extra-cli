# Implementation Plan — Historical Contracts Operational Coverage

**Branch**: `campaign/historical-contracts-operational-closure-01`  
**Date**: 2026-07-22

## Architecture (reuse first)

```
seed → source_policy applicability
     → contracts_crawler / 90d pilot / backfill_3y windows
     → pncp_supplier_contracts + checkpoints
     → contracts_entity_evidence adapter
     → coverage_evidence (canonical_entity_key + pncp/contracts roles)
     → dual_capability_coverage gate
     → weekly_cycle fail-closed + reports
```

## Work packages

1. **Applicability** — derive_esfera multi-nature + historical_contracts wildcard combination; policy 2.1.0 + hash.
2. **Evidence binding** — dual loads `canonical_entity_key`; migration 059 unique index; adapter CLI.
3. **Pilot live** — harden GO criteria; execute live 90d (not seal).
4. **Backfill 3y** — windowed crawl ≥1098d span; artifacts; then adapter with `window_complete` only if checkpoint proves all windows.
5. **Incremental** — watermark+overlap; weekly precondition.
6. **Product + CI** — reports, tests, independent review, honest DOD.

## Risks

| Risk | Mitigation |
|------|------------|
| PNCP 429 | pacing, checkpoint, multi-session resume |
| Fake success_zero | window_complete only after live proof; cleanup synthetic rows |
| Double-count pncp+contracts | shared run_id + documented roles |
| sc_public_entities empty | canonical_entity_key path |

## Out of scope

open_tenders 95%, VPS, new dual formula, PR mass-merge.
