# Live weekly proof — ARCH-RESET-2026-07-20

**Environment:** local PostgreSQL (`extra-test-db` :5433) + host network  
**DSN:** `LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test`  
**Migrations:** applied 61 (upgrade) before runs  

## Run A — offline / skip-collect (DB only)

| Field | Value |
|-------|--------|
| Command | `python3 -m scripts.ops.weekly_cycle --strict --offline --skip-collect --limit 20 --output-dir .../live-weekly` |
| cycle_id | `weekly-20260720T123255Z-2bd96bbea3` |
| collection_id | `col-extra-weekly-20260720T123255Z-11535c15` |
| exit_code | **2** (not consultively reliable — empty lake / contracts fail) |
| opportunities | 0 |
| contracts | 0 |
| products | MD + Excel + manifest + checksums |
| pdf | RESIDUAL_NOT_GENERATED |
| human_accept | PENDING_HUMAN |

Artifacts: `docs/ops/campaigns/ARCH-RESET-2026-07-20/evidence/live-weekly/`

## Run B — limited live collect (network)

| Field | Value |
|-------|--------|
| Command | `python3 -m scripts.ops.weekly_cycle --strict --limit 5 --force-collect --output-dir .../live-weekly-collect` |
| cycle_id | `weekly-20260720T123303Z-da1515c9a6` |
| collection_id | `col-extra-weekly-20260720T123303Z-1bce5af6` |
| exit_code | **0** |
| duration | ~111s |
| opportunities | **1** |
| contracts | **0** (pncp_contracts terminal_status=failure) |
| blockers observed | PNCP timeouts, HTTP 502/503/429 retries |
| pdf | RESIDUAL_NOT_GENERATED |
| human_accept | PENDING_HUMAN |

Artifacts: `docs/ops/campaigns/ARCH-RESET-2026-07-20/evidence/live-weekly-collect/`

## Claims

**Allowed**
- Live cycle executed against real PNCP endpoints with real PG.
- Failures (contracts 429/503) recorded; not hidden.
- Pack MD/Excel/manifest share cycle/collection ids.

**Forbidden**
- LOCAL_READY, operational coverage 95%, VPS_OPERATIONAL, PROJECT_DONE.
- Full suite green.
- PDF complete product.

## Residual

- Contracts source degraded.
- Universe not fully re-collected (limit 5).
- Human acceptance pending.
