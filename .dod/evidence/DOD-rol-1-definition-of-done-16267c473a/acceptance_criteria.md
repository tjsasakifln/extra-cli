# O golden path sobe ou valida o banco

Given make golden-path / scripts.golden_path
When step 1 runs check_db(dsn)
Then PostgreSQL connectivity is validated (fail-closed if down)
And make golden-path runs db-up + bootstrap before the pipeline
