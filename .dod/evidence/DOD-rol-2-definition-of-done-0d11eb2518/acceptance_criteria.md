# O crawl de editais atende freshness <= 24h.

## Given/When/Then
- Given SLA editais 24h (weekly + policy)
- When dual coverage open_tenders is measured
- Then fresh_count covers universe within SLA window for monitored entities

## Evidence
- Campaign OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01
- SHA 475aa50c7ab7ddfd93dd832ee4e8c53314bcacd4
- Artifacts under artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/
