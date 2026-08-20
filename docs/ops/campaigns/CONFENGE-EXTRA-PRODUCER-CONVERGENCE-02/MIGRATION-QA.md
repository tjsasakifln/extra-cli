# MIGRATION-QA

Ephemeral Postgres via `pgserver` (not Docker). DSN used only in the
local process; not committed.

## Occupancy

- `097_national_coverage.sql` already on `origin/main` with #437. Not edited.
- Additive `098_national_coverage_consumer_select_only.sql` makes
  `public.national_coverage_consumer_v1` non-insertable (`is_insertable_into=NO`)
  and grants SELECT / revokes mutation.

## Runner

```
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN" --min 97 --max 98 --mode upgrade
applied 097_national_coverage.sql
applied 098_national_coverage_consumer_select_only.sql
migrations_ok mode=upgrade applied=2 skipped=0 repaired=0
```

Reapply: `applied=0 skipped=2` (ledger). Idempotent.

## Objects

Tables: `national_coverage_universe`, `national_coverage_partition`,
`national_coverage_corpus_snapshot`, `national_coverage_answer`.
View: `public.national_coverage_consumer_v1`.
Constraint `national_coverage_universe_not_extra_1093` present.
Indexes: pkey + `national_coverage_universe_kind_hash_uidx`,
`national_coverage_partition_universe_idx`, `national_coverage_answer_lookup_idx`.

EXPLAIN: seq scan on `national_coverage_answer` through the consumer view
(toy rows; no 4.5M rewrite).

## Rollback / reapply

098 down → 097 down → 097 up → 098 up. View remains `is_insertable_into=NO`.

## real_db

`tests/national_coverage/test_persist.py::test_persist_and_select_on_real_postgres`
ran with `REQUIRE_REAL_DB=1`. Skip is not pass. Persist, SELECT, extra_1093
insert refused, consumer view mutation refused.

Log: captured under the implementer scratch `migration-qa.log`.
