# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T16:09:55Z  
**Status global:** **PARTIAL**

## Métricas honestas (recovery rebuild concluído no proxy contratos)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **313/1352 (23.1509%)** | ≥55% |
| Universo 200km | **1093** | — |
| Presença editais | **279 (25.5261%)** | ≥95% |
| Presença contratos | **329 (30.1006%)** | — |
| success_zero contratos | **722** | — |
| **Ops proxy contratos** | **1051/1093 (96.1574%)** | ≥95% **ATINGIDO** (proxy) |
| bids / contracts rows | 10831 / 409490 | — |

## Definição ops proxy

```
ops_proxy = lake presence(orgao_cnpj8) OR entity success_zero(cnpj14 root + http_204_complete)
```
**Não é** cobertura operacional de 7 estágios.

## Recovery session

- WSL crash → inventário + safety patch + push branch remota
- DB restore M5 + migrations; SZ waves + contracts expand rebuild
- DECISION-002: COV-EDIT-CONTRACT-OPS sobre dyn-slice docs
- N09 **BLOCKED_SOURCE**
- Editais presença ~25% permanece gap principal
- Campanha **PARTIAL** (DOD 55% e editais 95% abertos)

## Claims

**Permitidos:** ops proxy contratos ≥95% sob definição acima (medido 96.1574%).  
**Proibidos:** DONE · editais 95% · DOD 55% · LOCAL_READY · either · 7 estágios
