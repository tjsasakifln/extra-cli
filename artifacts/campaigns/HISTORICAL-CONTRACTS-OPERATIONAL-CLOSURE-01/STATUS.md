# Campaign STATUS — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Updated:** 2026-07-22  
**Branch:** `campaign/historical-contracts-operational-closure-01`  
**Commits:** `90e8fde` → `c4db215` → `53acd5a` → (90d pilot artifact)

## Result so far (honest)

| Gate | Status |
|------|--------|
| Baseline inventory | DONE |
| Spec 002 | DONE (skeleton + tasks) |
| Applicability 100% | **DONE** — unknown=0, denom=1093 |
| Dual measurement regression | DONE (38 unit tests pass) |
| Entity evidence adapter | DONE (infra; not live 3y projected) |
| Live 7d pilot | **DONE** success |
| Live 90d pilot | **DONE** success, **go_no_go_3y=GO** |
| Live 3y backfill | **RUNNING** (checkpoint `hc_closure_3y`) |
| Incremental command | DONE (`run_contracts_incremental`) |
| Weekly fail-closed contracts | DONE (`--strict` + optional `--contracts-incremental`) |
| Dual ≥95% operational | **NOT YET** — needs 3y windows complete + entity projection |
| DOD update | **NOT YET** — only after proof |
| Claim OPERATIONAL_COVERAGE_PASS | **FORBIDDEN until dual gate + evidence pack** |

## Resume commands

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test

# Resume 3y if interrupted (do NOT --reset-checkpoint)
python3 -m scripts.crawl.run_contracts_90d_pilot \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --days 1098 \
  --checkpoint-dir data/contracts_checkpoints/hc_closure_3y \
  --output-json artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/live-3y.json

# After backfill success, project entity evidence (window_complete only if all windows ok)
python3 -m scripts.coverage.contracts_entity_evidence \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --run-id "backfill-$(date -u +%Y%m%dT%H%M%SZ)" \
  --period-start YYYY-MM-DD --period-end YYYY-MM-DD \
  --window-complete --write \
  --output-json artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/entity-projection.json

# Dual reproof
python3 -m scripts.coverage.dual_capability_coverage --dsn "$LOCAL_DATALAKE_DSN" --capability historical_contracts

# Incremental
python3 -m scripts.crawl.run_contracts_incremental --dsn "$LOCAL_DATALAKE_DSN" --days 7
```

## Non-claims

- No LOCAL_READY / VPS / PROJECT_DONE  
- No open_tenders 95%  
- No operational 95% until live projection after 3y  
- Synthetic success_zero tests are not production evidence  

## Next

1. Wait / resume 3y backfill to completion  
2. Project entity coverage_evidence with proven window_complete  
3. Dual gate ≥95%  
4. Incremental idempotency + recovery proofs  
5. Independent review + DOD  
