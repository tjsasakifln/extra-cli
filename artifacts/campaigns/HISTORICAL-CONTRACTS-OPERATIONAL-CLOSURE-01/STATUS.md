# Campaign STATUS — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Updated:** 2026-07-22 (~7h into live 3y crawl)  
**Branch:** `campaign/historical-contracts-operational-closure-01`  
**Commits on branch:** `90e8fde`, `c4db215`, `53acd5a`, `21310cb`, `d49b103` (+ STATUS updates)

## Result so far (honest — NOT final PASS)

| Gate | Status |
|------|--------|
| Baseline inventory | DONE |
| Spec 002 | DONE (skeleton + tasks) |
| Applicability 100% | **DONE** — unknown=0, denom=1093 |
| Dual measurement regression | DONE (38 unit tests pass) |
| Entity evidence adapter | DONE (infra + real_db test) |
| Live 7d pilot | **DONE** success |
| Live 90d pilot | **DONE** success, **go_no_go_3y=GO** (~80min, 1001 pages, 467k inserts) |
| Live 3y backfill | **IN PROGRESS** — ~20/37 windows complete; ~4 partial/failed windows (PNCP 503/timeout/400) **not** marked complete; process PID live; auto-resume loop armed |
| Incremental command | DONE (`run_contracts_incremental`) |
| Weekly fail-closed contracts | DONE (`--strict` + optional `--contracts-incremental`) |
| Dual ≥95% operational | **NOT YET** — needs all 37 windows complete + entity projection |
| DOD update | **NOT YET** |
| Claim `HISTORICAL_CONTRACTS_OPERATIONAL_COVERAGE_PASS` | **FORBIDDEN** until dual gate + live projection |

## Live 3y checkpoint (snapshot)

- Checkpoint dir: `data/contracts_checkpoints/hc_closure_3y/`
- Artifact (running/partial): `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/live-3y.json`
- Log: `.../backfill/live-3y.log`
- Planned windows: **37** × 30d over 1098 days
- Completed windows: **~20** (rising)
- Failed counter: **~4** (windows left incomplete on purpose — retriable)
- Fetched/upserted: **~1.6M+** rows into `pncp_supplier_contracts`
- PNCP flakiness observed: 429/timeouts earlier, **503**, **500 DB**, occasional **400** path bugs on API

Incomplete windows are **not** sealed as complete (correct fail-closed). Resume without `--reset-checkpoint` re-attempts them.

## Resume (after interrupt)

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test

# Resume 3y (NO --reset-checkpoint)
python3 -m scripts.crawl.run_contracts_90d_pilot \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --days 1098 \
  --checkpoint-dir data/contracts_checkpoints/hc_closure_3y \
  --output-json artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/live-3y.json

# When completed_windows == 37 and windows_failed==0 in final artifact:
python3 -m scripts.coverage.contracts_entity_evidence \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --run-id "backfill-3y-$(date -u +%Y%m%dT%H%M%SZ)" \
  --period-start $(python3 -c "from datetime import date,timedelta; e=date.today(); s=e-timedelta(days=1097); print(s)") \
  --period-end $(date -u +%Y-%m-%d) \
  --window-complete --pages-processed 1 --pages-expected 1 \
  --write \
  --output-json artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/entity-projection.json

python3 -m scripts.coverage.dual_capability_coverage \
  --dsn "$LOCAL_DATALAKE_DSN" --capability historical_contracts

python3 -m scripts.crawl.run_contracts_incremental --dsn "$LOCAL_DATALAKE_DSN" --days 7
```

## Non-claims

- No LOCAL_READY / VPS / PROJECT_DONE  
- No open_tenders 95%  
- No operational 95% until live projection after **all** 3y windows  
- Synthetic success_zero unit tests ≠ production evidence  
- 90d GO ≠ 3y complete  

## Next (automatic when crawl finishes)

1. Resume until missing windows = 0  
2. Project entity `coverage_evidence` with `window_complete`  
3. Dual gate historical_contracts ≥95%  
4. Incremental + idempotency proofs  
5. Independent review + honest DOD  
