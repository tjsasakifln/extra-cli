# ADR-021 — Adapter Architecture + Fail-Closed (retroativo Reversa)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Fonte** | `docs/architecture/adr/ADR-021-adapter-architecture-pncp-429-fail-closed.md` |
| **Implementação** | `scripts/crawl/resilience/`, `scripts/ops/resilient_cycle.py`, mig 054 |
| **Confiança** | 🟢 CONFIRMADO |

## Contexto
Contratos de crawler heterogêneos; 429 PNCP; falsos success com janela incompleta.

## Decisão
Contrato `SourceAdapter` + `FetchResult` tipado; 429→rate_limited; pages incompletas→partial; empty_confirmed único zero-ok; raw antes de normalize.

## Consequências
Local resilience pré-VPS com filesystem SoT; projeção SQL satisfatória restrita; chaos tests obrigatórios.
