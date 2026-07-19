# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T14:43:27Z  
**HEAD:** ver `git log -1`  
**Status global:** **PARTIAL**

## Métricas honestas (recovery rebuild)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **313/1352 (23.1509%)** | ≥746 (55%) |
| Universo 200km | **1093** | — |
| Presença editais | **279 (25.5261%)** | ≥1039 |
| Presença contratos | **247 (22.5984%)** | — |
| success_zero contratos | **297** | — |
| **Ops proxy contratos** | **544/1093 (49.7713%)** | ≥95% |
| Gap ops→95% | **494** | — |

## Recovery notes

- Pre-crash ops proxy 100% lost after empty-DB restart; rebuild via SZ + lake presence.
- sc_compras enrich: editais presence 25.5%.
- SZ batches in progress; PNCP/contracts crawls may hit 429.
- DECISION-002: COV-EDIT-CONTRACT-OPS over dyn-slice docs.
- N09 **BLOCKED_SOURCE**.

## Claims

**Permitidos:** valores medidos acima sob definição de ops proxy.  
**Proibidos:** DONE · editais 95% · DOD 55% · LOCAL_READY · either · 7 estágios · ops proxy 100% sem medição atual
