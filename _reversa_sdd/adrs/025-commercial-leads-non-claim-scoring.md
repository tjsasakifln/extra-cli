# ADR-025 — Commercial leads: scoring multi-bucket com non-claim

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
Fila comercial de fornecedores precisava de ranking explicável sem alegar conversão estatística.

## Decisão
Módulo `commercial_leads` com signals → multi-bucket offer selection v4, margem mínima 0.10, limite flip single-signal 0.50, persistência em ledger (mig 062), supplier_registry (063) never-invent.

## Consequências
- UI/export deve carregar language_note de non-claim.
- NOT_COMPUTABLE é estado de primeira classe.
