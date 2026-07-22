# O golden path gera relatório de concorrentes

## Acceptance (registered before implementation)

Given a DSN with contract/bid data (or honest empty with limitations)
When golden_path runs concorrentes report (`--execute-concorrentes-report-only` or full path)
Then a report file is produced under `output/reports/`
And the file size >= 50 bytes (header-only OK with limitations)
And columns include at least concorrente_id, n_contratos
And the report is distinct from panorama Excel/PDF and from editais/contratos reports
And metadata includes git_sha, as_of, limitations
And automated tests prove the above without claiming 95% coverage

## OUT of scope
- Live crawl; LOCAL_READY; 95%; editais/contratos/valores items
