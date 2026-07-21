# O golden path persiste dados

Given clean PostgreSQL with migrations + seed
When essential sources execute via golden path
Then at least one source reports inserted+updated+persisted > 0
And ledger records persist_source_data pass
And rows exist in raw tables (e.g. pncp_raw_bids)

Not accepted on dirty/partial schema DBs without writes.
