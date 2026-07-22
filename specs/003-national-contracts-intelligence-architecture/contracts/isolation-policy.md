# Isolation Policy Contract

## MUST

- Worktree: `/mnt/d/extra-consultoria-national-intelligence` (or successor path for same branch)
- Branch: `campaign/national-contracts-intelligence-architecture-01`
- Base: accepted `origin/main` SHA documented in STATUS
- Default DSN: isolated DB on port **5435**, database `extra_national_intelligence_test`
- Artifacts: only under `artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/`

## MUST NOT

- Write `data/contracts_checkpoints/hc_closure_*`
- Write `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/`
- Kill/restart backfill process or `extraconsultoria-test-db-1`
- Run `--reset-checkpoint` against HC checkpoints
- Execute multi-year national backfill for “demo”
- Apply migrations to `extra_test` on 5433 from this campaign tooling
- Mark DOD operational coverage complete based solely on this campaign

## READ-ONLY optional

Short `SELECT`/`pg_relation_size` on 5433 only when necessary for inventory; no DDL, no long transactions, no ANALYZE storms during live write.
