# A integridade do snapshot ativo é 100%.

## Given/When/Then
- Given PostgreSQL VPS com opportunity_intel + opportunity_runs + membership
- When measure_snapshot_integrity(dsn) roda sobre snapshot ativo open/upcoming
- Then integrity_pct == 100.0 e operational_ok == true e active_open_count > 0
- And existe parent run completed+scope_complete

## Evidence
- Campaign OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01
- SHA 475aa50c7ab7ddfd93dd832ee4e8c53314bcacd4
- Artifacts under artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/
