# O golden path executa fontes mínimas

## Given/When/Then
Given DB connectivity
When `python3 -m scripts.golden_path --execute-sources-only` runs
Then each essential adapter (pncp, pcp, compras_gov) is invoked via crawl_source → monitor.py
And ledger records SourceRecord with attempts>=1 for each
And proof is NOT a static SOURCES list characterization
And adapter fail still counts as executed (persist is a separate DOD item)

## Evidence
- CLI --execute-sources-only live ledger
- tests/test_golden_path_fontes_minimas.py
- crawl_source honors JSON failed status (no silent success)
