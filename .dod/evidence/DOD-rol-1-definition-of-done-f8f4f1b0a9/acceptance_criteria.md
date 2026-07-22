# O golden path gera relatório de contratos

## Acceptance (registered before implementation)

Given a DSN with pncp_supplier_contracts (or honest empty with limitations)
When golden_path runs contratos report step (`--execute-contratos-report-only` or full path)
Then a report file is produced under `output/reports/` (or documented path)
And the file is not empty (size >= 50 bytes; header-only OK with limitations)
And the report contains contract-specific columns: at least ente_id, n_contratos, valor_total
And the report is distinct from generic panorama Excel/PDF and from editais report
And metadata includes generation timestamp, code version (git_sha), and limitations
And a specific automated test proves the above without claiming 95% coverage

## OUT of scope
- Live PNCP crawl
- Relatório de editais/concorrentes/valores (separate items)
- LOCAL_READY / 95%
