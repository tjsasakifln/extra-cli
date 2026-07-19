# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T15:30:33Z  
**Status global:** **PARTIAL**

## Métricas honestas (recovery rebuild)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **313/1352 (23.1509%)** | ≥55% |
| Universo 200km | **1093** | — |
| Presença editais | **279 (25.5261%)** | ≥95% |
| Presença contratos | **307 (28.0878%)** | — |
| success_zero contratos | **522** | — |
| **Ops proxy contratos** | **829/1093 (75.8463%)** | ≥95% |
| Gap ops→95% | **209** | — |
| bids / contracts rows | 10831 / 238859 | — |

## Recovery

- WSL crash → branch pushada; DB restore M5; SZ rebuild + contracts expand.
- Pre-crash ops proxy 100% **não** reafirmado até ≥95% medido de novo.
- DECISION-002: COV-EDIT-CONTRACT-OPS. N09 BLOCKED_SOURCE.
- Editais permanecem principal gap de presença.

## Claims

**Permitidos:** valores acima sob definição de ops proxy.  
**Proibidos:** DONE · editais 95% · DOD 55% · LOCAL_READY · either · 7 estágios
