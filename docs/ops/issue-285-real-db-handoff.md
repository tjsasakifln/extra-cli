# Issue #285 — `real_db` reliability handoff

**Status:** `VERIFIED` on branch; `ACCEPTED` requires exact-HEAD CI and merge to
`main`.

## Reproduce

Provision a disposable local PostgreSQL 16+ instance with pgvector and a user
that has `CREATEDB`, then run:

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m scripts.ops.run_full_suite --real-db-only --repeat 2
```

The runner creates a new sibling database for each repetition, applies every
canonical migration and both required seeds, validates the real connection and
schema ledger, runs `REQUIRE_REAL_DB=1 pytest tests/ -m real_db`, and always
drops the generated database. The second repetition reverses collection order.

## Failure ledger

| Baseline node/result on current `main` | Classification | Root cause and resolution | After |
|---|---|---|---|
| `TestSeedCoverage::test_all_secretarias_have_alias` failed | seed/fixture | Entity seed absent; strict seed bootstrap plus cardinality preflight | Pass |
| `TestSeedCoverage::test_alias_count_matches_expected` failed | seed/fixture | Alias seed absent; both mandatory seeds now fail closed | Pass |
| `test_dual_seed_and_bid_table_no_duplicate_keys` failed | seed/fixture | Idempotency test received an unseeded DB; canonical seeds now precede collection | Pass |
| `test_clean_env_confirm_drop_runs` failed | tooling/psql | Hidden `psql` dependency replaced by required psycopg2 administration | Pass |
| `test_linkage_pipeline_on_isolated_dsn` skipped | lifecycle / isolation | Module DSN and fixed-port gate bypassed the canonical DB; generated DB is accepted and data is owned/cleaned | Pass |
| `test_population_stats_full_not_sample` skipped | seed/fixture / isolation | Campaign DB was assumed pre-restored; module now seeds deterministic material rows in the per-run DB | Pass |
| `test_run_pack_end_to_end_real_path` skipped | seed/fixture / isolation | Same external campaign-state dependency; shared fixture now owns setup and cleanup | Pass |
| Cross-module residual exposed during repair | leak de estado / order | Linkage/report rows contaminated later presence checks; producers clean their rows and clean-lake tests require the generated DB | 132 pass twice |

No migration/schema drift, timezone/clock defect, or production-code defect was
observed in the current-main residual. Those classes remain covered by the
strict ledger, real-connection, and reverse-order preflights.

Current-main revalidation before the fix collected 131 selected tests and
reported **124 passed, 4 failed, 3 skipped**. The historical issue record
reported 115 passed, 6 failed, and 1 error; the difference comes from changes
already present on current `main`, not from hiding tests.

Branch verification after the fix selected 132 tests. Both the normal-order and
reverse-order runs reported **132 passed, 0 failed, 0 errors, 0 skipped**. Each
run applied 103 migration files (104 exact ledger entries), loaded 2,085 entities
and 459 active aliases, and verified a real psycopg2 connection before pytest.
The canonical unfiltered runner was also exercised on a generated database and
reported **6,035 passed, 139 optional skips, 0 failed, 0 errors**; those optional
skips are not part of the `real_db` acceptance count.

## Enforced invariants

- no production/soak or non-local DSN;
- no database reuse and no pre-existing schema;
- no missing migration or checksum drift;
- no missing entity or alias seed;
- no fake/mock connection under opt-in;
- no `real_db` skip after admission;
- no `psql` requirement; missing psycopg2 is a named tooling failure.

No refresh, feed, campaign, or production operation is part of this proof.
