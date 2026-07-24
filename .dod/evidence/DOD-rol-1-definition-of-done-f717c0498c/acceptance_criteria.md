# source_applicability_resolution = 100%.

## Given/When/Then
- Given policy source_applicability.yaml active v2.1.1
- When dual_capability_coverage open_tenders is regenerated
- Then applicability_unknown_count == 0 and applicable_denominator == universe_count

## Evidence
- Campaign OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01
- SHA 475aa50c7ab7ddfd93dd832ee4e8c53314bcacd4
- Artifacts under artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/
