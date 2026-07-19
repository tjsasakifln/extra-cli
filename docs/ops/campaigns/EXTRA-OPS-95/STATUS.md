# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T16:21:16Z  
**HEAD:** `0a4fa0a8f74d` · branch `campaign/extra-ops-95-20260719`  
**Status global:** **PARTIAL**

## Métricas honestas (closeout recovery)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **313/1352 (23.1509%)** | ≥55% |
| Universo 200km | **1093** | — |
| Presença editais | **279 (25.5261%)** | ≥95% |
| Presença contratos | **329 (30.1006%)** | — |
| success_zero contratos | **722** | — |
| **Ops proxy contratos** | **1051/1093 (96.1574%)** | ≥95% **ATINGIDO** (proxy) |
| Gap ops→95% | **0** | — |
| bids / contracts rows | 10831 / 409490 | — |

## Definição ops proxy

```
ops_proxy = lake presence(orgao_cnpj8) OR entity success_zero(cnpj14 root + http_204_complete)
```

**Não é** cobertura operacional de 7 estágios.

## Recovery closeout

- Branch remota: `origin/campaign/extra-ops-95-20260719` @ `0a4fa0a8f74d`
- WSL crash → inventário + safety + push; DB restore M5; SZ + contracts expand
- DECISION-002: COV-EDIT-CONTRACT-OPS
- N09 **BLOCKED_SOURCE**
- Editais ~25% e DOD ~23% abertos → campanha **PARTIAL**

## Claims

**Permitidos:** ops proxy contratos ≥95% sob definição acima (96.1574%).  
**Proibidos:** DONE · editais 95% · DOD 55% · LOCAL_READY · either · 7 estágios
