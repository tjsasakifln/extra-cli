# Fix — Tasks

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

| # | Tarefa | Confiança |
|---|--------|-----------|
| T-FX01 | Auditar `rebuild_evidence_ledger.py` — documentar algoritmo completo | 🟡 |
| T-FX02 | Auditar `resolve_unresolved_entities.py` — documentar matching cascade | 🟡 |
| T-FX03 | Auditar scripts restantes (5) — documentar propósito e pré-condições | 🟡 |
| T-FX04 | Adicionar testes de regressão para rebuild_evidence_ledger | 🔴 |
| T-FX05 | Adicionar testes de regressão para resolve_unresolved_entities | 🔴 |
| T-FX06 | Garantir idempotência: cada script pode ser reexecutado sem dano | 🟡 |

**Estimativa:** 5-8 dias (6 tarefas, ~165K LOC para auditar)
