# A versão do schema é registrada.

Given golden_path CLI runs and writes a ledger
When _save_final_ledger executes
Then run.meta contains schema_version from collect_run_metadata
And the value is non-empty in the ledger JSON (not merely a function definition)
