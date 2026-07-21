# O golden path executa freshness gate

Given reachable DSN
When `python3 -m scripts.golden_path --execute-freshness-only` runs
Then freshness_gate.py is invoked as subprocess
And ledger records run_freshness_gate with structured details
And status pass OR fail both count as executed
And skip without running is not acceptance

Note: contracts=never is a fail status but still proves execution.
Pass/SLA is a separate DOD item.
