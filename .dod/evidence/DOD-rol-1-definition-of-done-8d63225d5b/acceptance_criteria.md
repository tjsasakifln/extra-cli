# A versão do código é registrada.

Given golden_path CLI runs and writes a ledger
When _save_final_ledger executes
Then run.meta contains git_sha from collect_run_metadata
And the value is non-empty in the ledger JSON (not merely a function definition)
