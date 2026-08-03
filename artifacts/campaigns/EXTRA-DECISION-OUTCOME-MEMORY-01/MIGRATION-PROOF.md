# Migration proof

- File: `db/migrations/068_decision_outcome_memory.sql`
- Applied on local PostgreSQL 18.4 @ 127.0.0.1:5433
- Re-apply via `python3 -m scripts.ops.apply_migrations --dsn $LOCAL_DATALAKE_DSN` → skipped (ledger), exit 0
- Note: local DB previously had orphaned version 068 from unmerged PR #197 (`068_predictive_intelligence.sql`); reconciled by applying decision-memory SQL and updating `_migrations.name`

See also scratch log (session): migration-proof.log
