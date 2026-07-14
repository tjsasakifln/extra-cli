# ADR-012: QW-01 Radar Operacional — PostgreSQL-only, Determinístico

**Data:** 2026-07-12
**Status:** Aceito
**Autor:** QW-01 Implementation (commits ce55095, 249340d)
**Stakeholders:** Extra Consultoria

---

## Contexto

O sistema precisava de um radar operacional de licitações abertas que produzisse um CSV auditável, com pontuação explicável e rastreável. Requisitos:

1. Execução em batch, sem dependência de LLM em runtime
2. Toda decisão de scoring rastreável a uma regra documentada
3. Output auditável com git SHA, schema fingerprint, seed SHA-256
4. Threshold mínimo de cobertura para validade do radar

## Decisão

Implementar QW-01 como pipeline PostgreSQL-only com scoring determinístico:

- **Monitoring threshold: 95%** — abaixo disso, exit code 2 (fail-closed)
- **6 HARD_BLOCKS** — status terminal, data passada, sem objeto, sem órgão, valor negativo, fora do raio
- **9 POSITIVE factors** — status open (+30), data futura (+15), órgão conhecido (+10), etc.
- **9 NEGATIVE factors** — status unknown (-20), sem data (-15), fonte baixa confiança (-10), etc.
- **Baseline: 50 pontos** — ajustado por fatores positivos/negativos
- **Triagem:** GO (≥70), REVIEW (40-69), NO_GO (<40)
- **NUNCA emitir veredito definitivo** de participação — sempre triagem para humano

## Consequências

- Radar é totalmente determinístico e auditável — nenhuma decisão "inexplicável"
- Threshold 95% é conservador: fontes bloqueadas (7) impedem atingir 100%
- QW-01 é ponta da lança da vertical de Opportunity Intelligence — contratos (Contract Intel) são vertical separada
- Pipeline monoliticamente PostgreSQL: sem Redis, sem fila, sem worker externo
