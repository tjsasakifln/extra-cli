# SMARTLIC REUSE MATRIX — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T20:41:29Z  
**SmartLic commit:** `93ea19630d745d5b90d3b1657261ee88e99bc065` (read-only clone `/tmp/SmartLic-readonly`)  
**Mode:** no submodule · no runtime dependency · no SaaS import

## Classification summary

| ID | Asset | Class | Action |
|----|-------|-------|--------|
| SL-A01 | contracts_crawler | EXTRA_VERSION_SUPERIOR | Do not port |
| SL-A02 | checkpoint | PATTERN_ONLY | Audit page resume |
| SL-A03 | snapshot tables | DATA_BRIDGE | **Import bridge** |
| SL-A04 | PNCP fixtures | PORT_FIXTURE | Selective |
| SL-A05 | classification corpus | PORT_FIXTURE | Benchmark |
| SL-A06 | frontend/auth/billing | REJECT_COMPLEXITY | Reject |
| SL-A07 | Redis/ARQ/multi-tenant | INCOMPATIBLE | Reject |
| SL-A08 | high-volume pagination | PATTERN_ONLY | Evaluate |
| SL-A09 | report helpers | PATTERN_ONLY / ALREADY | Keep Extra |
| SL-A10 | pncp_raw_bids schema | ALREADY_PRESENT | None |

## Non-negotiable

- Snapshot ≠ live · presence ≠ coverage · history ≠ freshness
- Extra must run its own incremental after any import
- No secrets in repo; bridge works offline with exported JSON
