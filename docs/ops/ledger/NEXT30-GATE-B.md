# NEXT30-GATE-B — DATA_EXPANSION

**Date:** 2026-07-17  
**Verdict:** **PASS WITH PARTIALS**

| Check | Result | Evidence |
|-------|--------|----------|
| sc_compras ingested | **PASS** | 2602 fetched/inserted; `output/sc_compras/runtime-next30d.json`; baseline `c2.7-sc-compras-runtime-next30d.md` |
| DOE-SC | **BLOCKED_EXTERNAL** | Credentials not available |
| PNCP contracts 90d pilot | **PARTIAL** | ≥6050 contracts mid-run; checkpoint present; final JSON pending |
| Checkpoint/resume machinery | **PASS** (code+file) | `data/contracts_checkpoints/contracts_full.json`; partial-window fix |
| Dedup cross-source integrated | **PASS** | CLI `run_dedup.py`; `dedup_cross_source` ≥3–5 rows; `c2.8-dedup-wired-next30d.md` |
| Coverage recalculated | **PASS (honest)** | editais crude ~4.76% (52/1093); contracts presence rising, not 95% |

## Exit

Gate B **partial pass** — public data expansion executed; DOE blocked; contracts pilot not closed.
