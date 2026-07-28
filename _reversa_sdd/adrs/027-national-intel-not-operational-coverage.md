# ADR-027 — National intel layers ≠ coverage operacional SC

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
Produtos de inteligência nacional (competitors/agencies/benchmarks) não devem ser vendidos como cobertura operacional do universo SC 200 km.

## Decisão
Views L1/L2/L3 em mig 060 + CLI `national_intel` com claim class `intel_product` / scope labels explícitos.

## Consequências
- Relatórios e DoD devem rotular escopo.
- UF=SC geográfico ≠ dual capability covered.
