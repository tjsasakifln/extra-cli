# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T08:15:04Z  
**HEAD:** ver `git log -1`  
**Status global:** **PARTIAL**

## Métricas honestas

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **270/1352 (19.9704%)** | ≥746 (55%) |
| Universo 200km | **1093** · resolution 100% | — |
| Presença editais | **285 (26.075%)** | ≥1039 |
| Presença contratos | **368 (33.6688%)** | — |
| success_zero contratos | **722** | — |
| **Ops proxy contratos** | **1090/1093 (99.7255%)** | ≥1039 (95%) **ATINGIDO** no proxy |
| Residual ops | **3** | PRF/DPF cnpj_8 malformado (14 dígitos) |

## Definição do ops proxy (explícita)

```
ops_proxy = entidades com (presença de orgao_cnpj8 no lake de contratos)
         OR (success_zero entity-scoped com cnpj14 raiz=cnpj8 + http_204_complete)
```

**Não é** cobertura operacional de 7 estágios.  
Método de identidade residual: `cnpj8+0001+DV` validado por **BrasilAPI** (nome soft-match) antes do probe PNCP.

## Residual (3)

Entes com `cnpj_8` de 14 dígitos (raiz 00394494 — PF/PRF SC) — bug de seed/planilha, não cobertos.

## Claims

**Permitidos:** ops proxy contratos ≥95% sob a definição acima.  
**Proibidos:** 7 estágios · editais 95% · DONE · DOD 55% · LOCAL_READY · either
