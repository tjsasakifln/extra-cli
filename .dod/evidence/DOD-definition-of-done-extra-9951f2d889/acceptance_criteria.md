# O relatório inclui editais comprovadamente abertos na data de corte ou semana de conclusão.

## Given/When/Then
- Given live deliverable E audit from opportunity_intel
- When audit_report(operational=True) runs
- Then check `open_at_cut` is PASS and recommendation_count > 0

## Evidence
- Campaign OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01
- SHA 475aa50c7ab7ddfd93dd832ee4e8c53314bcacd4
- Artifacts under artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/
