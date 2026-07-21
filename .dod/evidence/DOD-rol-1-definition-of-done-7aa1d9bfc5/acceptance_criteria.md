# O golden path aplica migrations

## Given / When / Then
- Given a reachable PostgreSQL DSN
- When `python3 -m scripts.golden_path` runs (without `--skip-migrations`)
- Then step `apply_migrations` invokes `scripts.ops.apply_migrations.apply_range` on `db/migrations`
- And re-run is idempotent (skipped ledger entries)
- And migration failure is fail-closed (exit != 0)

## Evidence
- Unit: tests/test_golden_path_canonical.py::test_apply_migrations_function_exists_and_uses_apply_range
- Live dual apply_migrations on isolated PG16
