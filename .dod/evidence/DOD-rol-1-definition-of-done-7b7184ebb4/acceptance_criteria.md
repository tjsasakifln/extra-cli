# O golden path gera relatório de referências de valores

## Acceptance

Given DSN with pncp_raw_bids (or honest empty + limitations)
When golden_path runs valores report (`--execute-valores-report-only` or full path)
Then domain file under output/reports with size>=50
And columns include modalidade, n, valor_semantica
And report distinct from panorama and other domain reports
And metadata: git_sha, as_of, limitations; no LOCAL_READY/95%/homologated claims
And specific automated tests pass

## OUT
- Live crawl; editais/contratos/concorrentes; 95%; homologated prices as fact
