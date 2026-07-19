# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T07:59:34Z  
**HEAD:** `760ce38+`  
**Status global:** **PARTIAL**

## Métricas honestas

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **270/1352 (19.9704%)** | ≥746 (55%) |
| Universo 200km | **1093** · resolution 100% | — |
| Presença editais | **285 (26.075%)** | ≥1039 |
| Presença contratos | **368 (33.6688%)** | ≥1039 |
| success_zero contratos | **623** | — |
| Ops proxy contratos | **991 (90.6679%)** | 1039 gap **48** |
| Residual contratos ops | **102** | identity blocker |

## Blocker de identidade (residual)

Probe matriz 0001 em 60 residual: **60/60 HTTP 404** no PNCP orgaos.

Classes: SECRETARIA 23 · CIA 31 · BANK 8 · ENERGY 9 · EMPRESA 10 · FUNDO 4 · GUARDA 3 · OTHER 14.

**Não** gravar success_zero sem cnpj14 oficial. **Não** inventar CNPJ.  
Evidência: `evidence/M2-cnpj14/residual-identity-classification.json`

## Claims proibidos

95% · 7 estágios · DONE · LOCAL_READY · either · auto-SZ residual · SmartLic operacional
