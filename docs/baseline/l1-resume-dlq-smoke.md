# L1.6 — Resume / DLQ / watermark smoke

**Story:** PE-L1-03  
**Data:** 2026-07-16

## Evidência de implementação (código)

DATA-FOUNDATION waves 0–4 entregaram DLQ, watermarks, provenance, chaos tests (ver `.aiox/epic-DATA-FOUNDATION-state.yaml`).

## Testes smoke (amostra)

| Suite | Resultado |
|-------|-----------|
| Part1 (chaos + core) | 817 passed, 15 failed, 18 errors, 5 skipped (~100s) |
| Part2a | 318 passed, 9 failed, 27 skipped |
| Part2b1 | 219 passed, 1 failed, 32 skipped |

Falhas não foram silenciadas; ver `docs/baseline/q5-critical-tests.md`.

## Veredito L1.6

**PARTIAL** — infraestrutura resume/DLQ presente e coberta por testes majoritariamente verdes; suite completa ainda tem falhas residuals (não GATE PASS total).
