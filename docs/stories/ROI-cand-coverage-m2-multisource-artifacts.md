# ROI-cand-coverage-m2-multisource-artifacts

## Objective
Advance M2 operational_source_coverage using multi-source crawl artifacts
(ciga_dom, sc_compras, pncp) with provenance, without claiming 95%.

## Result (honest, post fan-out fix)
- Before: **81/1.093**
- After: **90/1.093 (8.23%)**
- Delta: **+9**
- Sources: ciga_dom +2, sc_compras +6, pncp +1

## Code fix
`promote_from_pipeline_evidence` no longer fans one evidence row across all
registry siblings sharing a CNPJ-8. Prefers `entity_db_id`; CNPJ-8 fallback
requires unique registry root.

## Non-claims
No 95% coverage, no freshness global, no recall ≥95%, no READY seals, no VPS.
