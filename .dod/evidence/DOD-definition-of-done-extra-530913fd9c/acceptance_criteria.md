# Reconciliação de status de editais.

## Given/When/Then
- Given SourceSnapshotReconciler and complete aggregated run
- When reconcile runs with membership keys matching numero_controle_pncp
- Then absent only after complete run; false inactivation bug fixed for raw PNCP keys

## Evidence
- Campaign OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01
- SHA 475aa50c7ab7ddfd93dd832ee4e8c53314bcacd4
- Artifacts under artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/
