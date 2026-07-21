# O golden path gera relatório de editais

## Acceptance (registered before implementation)

Given a DSN with pncp_raw_bids (or honest empty with limitations)
When golden_path runs editais report step (`--execute-editais-report-only` or full path)
Then a report file is produced under `output/reports/` (or documented path)
And the file is not empty (size >= 100 bytes when rows exist; or documented empty + limitations)
And the report contains editais-specific columns: at least pncp_id, objeto_compra, orgao, uf
And the report is distinct from generic panorama Excel/PDF
And metadata includes generation timestamp, code version (git_sha), and limitations
And a specific automated test proves the above without claiming 95% coverage

## OUT of scope
- Live PNCP crawl (may use existing DB rows / fixtures)
- Relatório de contratos/concorrentes/valores (separate items)
- LOCAL_READY / 95%
