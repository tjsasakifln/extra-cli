# ADR-029 — Snapshot write guard opt-in (CONFENGE)

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
DBs restaurados de snapshot comercial não devem ser poluídos por inserts acidentais de testes/CI.

## Decisão
Trigger em `pncp_supplier_contracts` ativo só com `app.confenge_snapshot_guard=on`; mutação controlada via `app.allow_snapshot_mutation=on`.

## Consequências
- CI normal inalterado (guard off por default).
- Restore paths devem setar LOCAL allow.
