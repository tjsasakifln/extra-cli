# ADR-028 — ORPT: relatórios operacionais fail-closed + metadata unificada

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
DoD §12 exigia listas e relatórios analíticos + PDF/Excel com rastreabilidade, sem listas vazias mentirosas.

## Decisão
Vertical `reports/*`: operational_outputs/reports, domain reports §12.1, executive PDF/Excel, `run_metadata` sidecars, export pack.

## Consequências
- Dependência forte de schema presente.
- Comparação PDF↔Excel via metadata.
