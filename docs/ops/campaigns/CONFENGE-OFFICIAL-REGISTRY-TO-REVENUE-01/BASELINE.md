# Baseline — antes da campanha

**Capturado:** 2026-07-30  
**Fonte:** `artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/result.json`

| Métrica | Valor |
|---------|-------|
| contratos processados (hist.) | 4.467.364 |
| empresas candidatas | 22.882 |
| leads priorizados | 20 |
| official_registry_coverage | **0.0292** |
| supplier_registry_coverage | 1.0 |
| top10 official registry failures | 10 |
| terminal | BLOCKED / FAIL_TOP10_VALIDITY_OFFICIAL_CADASTRO |
| handoff | READY_FOR_TIAGO_REVIEW (humano pendente) |

## Código pré-existente reutilizado

- `scripts/commercial_leads/supplier_registry.py` — `is_official_registry_source`, `official_registry_coverage`
- `scripts/commercial_leads/canonical_coverage.py`
- `scripts/commercial_leads/top10_gate.py`
- `scripts/ops/confenge_official_cnpj.py` / `confenge_registry_ingest.py` (fallback paths; não autoridade RFB)
- `scripts/linkage/keys.py` — `is_valid_cnpj14`

## Inventário CNPJ (pré-implementação)

Fallbacks: BrasilAPI, MinhaReceita, cnpj.ws, OpenCNPJ bulk script.  
Oficial: markers RFB, mas **sem espelho local versionado ACTIVE**.
