# Multi-source M2 scale (clean rebuild)

**Story:** ROI-cand-coverage-m2-multisource-artifacts  
**M2 before:** 81/1093  
**M2 after:** **90/1093 (8.2342%)**  
**Delta:** +9  
**Claims 95%?** NO  

## Fix vs stacked PR #22

Original stacked tip claimed 93 via fan-out of one PNCP evidence row across
four registry entities sharing CNPJ-8 `00394494`. Integration audit rejected
that overcount. Code now prefers `entity_db_id` and requires unique registry
CNPJ-8 for fallback matching.

## Per source

See multi-result.json.

## Explicit non-claims

- No operational coverage 95%
- No freshness global ready
- No recall ≥95%
- No LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY / VPS operational / project done
