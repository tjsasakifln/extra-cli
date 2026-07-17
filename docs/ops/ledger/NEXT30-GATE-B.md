# NEXT30-GATE-B — DATA_EXPANSION

**Date:** 2026-07-17  
**Verdict:** **PASS** (only residual **BLOCKED_EXTERNAL**: DOE-SC)

| Check | Result | Evidence |
|-------|--------|----------|
| sc_compras ingested | **PASS** | 2602 fetched/inserted; `output/sc_compras/runtime-next30d.json` **status=success** (restored from `ea78064` after a failed re-run overwrote with esfera_id error — DB still holds 2602 `source=sc_compras` rows) |
| DOE-SC | **BLOCKED_EXTERNAL** | Owner: Tiago; cause: missing `DOE_SC_LOGIN`/`DOE_SC_PASSWORD`; prep: crawler ACTIVE in registry; next test: `validate_source_credentials` when secrets set |
| PNCP contracts pilot terminal | **PASS** | `output/contracts/pilot-90d-next30d.json` status=**success**, windows_ok≥1, page_errors=0; go path GO |
| Checkpoint/resume | **PASS** | `data/contracts_checkpoints/contracts_full.json` with completed window |
| Dedup integrated | **PASS** | CLI + `dedup_cross_source`>0 |
| Coverage recalculated | **PASS** | 4.76% editais crude; contracts 31219 |

V6.2 VPS remains **BLOCKED_EXTERNAL** (out of data gate; owner Tiago).
