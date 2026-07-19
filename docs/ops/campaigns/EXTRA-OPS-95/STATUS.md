# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T14:26:40Z  
**HEAD:** ver `git log -1`  
**Status global:** **PARTIAL**

## Métricas honestas (pós-recovery + restore M5 + re-probe)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **313/1352 (23.1509%)** | ≥746 (55%) |
| Universo 200km | **1093** · resolution 100% | — |
| Presença editais | **279 (25.5261%)** | ≥1039 |
| Presença contratos | **247 (22.5984%)** | — |
| success_zero contratos | **186** | — |
| **Ops proxy contratos** | **433/1093 (39.6157%)** | ≥1039 (95%) **NÃO atingido** pós-restore |
| Gap ops→95% | **605** | — |
| bids_rows / contracts_rows | 10831 / 72925 | — |

## Contexto recovery

- Terminal WSL encerrou; branch `campaign/extra-ops-95-20260719` recuperada e pushada (`4f2f55a`).
- DB local estava vazio; migrations + restore do dump M5 (estado intermediário overnight).
- Métricas pre-crash (ops proxy 100%, editais ~27%) **não** se aplicam ao lake atual até re-coleta/SZ completar.
- sc_compras enrich: presença editais 268→279.
- SZ contracts batch 200: 186 SUCCESS_ZERO escritos; ops proxy rebuild **39.62%**.
- PNCP full + contracts expand em curso (rate limit 429 observado).

## Definição do ops proxy (explícita)

```
ops_proxy = entidades com (presença de orgao_cnpj8 no lake de contratos)
         OR (success_zero entity-scoped com cnpj14 raiz=cnpj8 + http_204_complete)
```

**Não é** cobertura operacional de 7 estágios.

## ROI / decisões

- DECISION-001 + **DECISION-002**: override force-next dyn-slice docs → COV-EDIT-CONTRACT-OPS
- N09: **BLOCKED_SOURCE** (`evidence/M6-n09/BLOCKED_SOURCE.md`)
- Story dyn-slice `ROI-cand-dyn-slice-cb906bb58392` permanece Draft (não implementada)

## Claims

**Permitidos:** ops proxy em rebuild (valor medido acima); presença editais/contratos separadas.  
**Proibidos:** 7 estágios · editais 95% · DONE · DOD 55% · LOCAL_READY · either · ops proxy 100% sem re-medição atual
