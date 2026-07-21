# O golden path reconcilia snapshot de editais

Given pncp_raw_bids populated
When --execute-snapshot-only runs twice
Then first run creates baseline snapshot file with ids_sha256
And second run reports added/removed/changed counts
And not a connectivity-only probe
