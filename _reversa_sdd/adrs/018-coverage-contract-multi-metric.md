# ADR-018 — Coverage Contract Multi-Metric (retroativo Reversa)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Fonte** | `docs/architecture/adr/ADR-018-coverage-contract-multi-metric.md` |
| **Implementação** | `scripts/coverage/coverage_contract.py` |
| **Confiança** | 🟢 CONFIRMADO |

## Contexto
Métricas conflitantes destruíram confiança comercial (overclaim).

## Decisão
Contrato multi-métrica M1–M5; denominador fixo 1093; dual-headline M1×M2; list identity; stale → UNVERIFIED.

## Baseline sessão 2026-07-17
- M1: 116/1093 (10,61%)  
- M2 strict: 0/1093  

## Consequências
QA adversarial falha build se headline único sem dual-metric; meta 95% aplica-se a M2, não a M1.
