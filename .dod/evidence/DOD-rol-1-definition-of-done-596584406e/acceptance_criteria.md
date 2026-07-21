# O golden path pode ser executado em ambiente limpo

Given a disposable PostgreSQL database created from empty state
When migrations + seeds + golden_path run via `scripts.ops.golden_clean_env --confirm-drop`
Then recreate_db/migrations/seeds succeed, public_tables >= 5, golden_path exit 0
And no reuse of prior DB volume state for that database name
And claims forbid LOCAL_READY / 95% from this proof alone
