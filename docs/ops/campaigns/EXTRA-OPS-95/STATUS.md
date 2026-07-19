# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T08:25:00Z  
**HEAD:** ver `git log -1`  
**Status global:** **PARTIAL**

## Métricas honestas

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **313/1352 (23.15%)** | ≥746 (55%) |
| Universo 200km | **1093** · resolution 100% (`sc_public_entities.raio_200km`) | — |
| Presença editais | **299 (27.36%)** | ≥1039 |
| Presença contratos | **371 (33.94%)** | — |
| success_zero contratos | **722** | — |
| **Ops proxy contratos** | **1093/1093 (100%)** | ≥1039 (95%) **ATINGIDO** no proxy |
| Residual ops | **0** sob join entity_id∪presence (3 cnpj_8 malformados cobertos via raiz 8 se houver presença; seed ainda incorreto) | seed fix residual |

## Definição do ops proxy (explícita)

```
ops_proxy = entidades com (presença de orgao_cnpj8 no lake de contratos)
         OR (success_zero entity-scoped com cnpj14 raiz=cnpj8 + http_204_complete)
```

**Não é** cobertura operacional de 7 estágios.  
Método de identidade residual: `cnpj8+0001+DV` validado por **BrasilAPI** (nome soft-match) antes do probe PNCP.

## ROI cycle ativo

- `cand-dyn-slice:ac8b6e76a7b2` — §25 PARTIAL/BLOCKED semantics (PARTIAL_SEMANTICS + tests)

## Claims

**Permitidos:** ops proxy contratos ≥95% (agora 100%) sob a definição acima.  
**Proibidos:** 7 estágios · editais 95% · DONE · DOD 55% · LOCAL_READY · either
