---
story_id: B2G-E1.S1
title: "Coverage contract multi-metric (M1–M5) + rename commercial signal"
status: InProgress
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E1
depends_on: []
blocks: [B2G-E1.S2, B2G-E4.S1]
adr: [ADR-018]
---

# Story B2G-E1.S1: Coverage contract multi-metric + rename

## Contexto

A sessão 2026-07-17 estabilizou o headline comercial em **116/1093** (`list_identity_ok`), mas o nome legado `commercial_opportunity_any` e a confusão com “cobertura 95%” permanecem. Precisamos do **contrato multi-métrica** (ADR-018) no código e nos outputs.

**Baseline:** `entities_with_recent_commercial_signal` = 116/1093 (10,61%).  
**Meta 95%:** aplica-se a `operational_source_coverage` (M2), **não** a M1.

## Valor de negócio

Impede overselling; torna todo relatório e o workspace auditáveis; desbloqueia E1.S2 e E4 coverage.

## Escopo

**IN:** Schema de métricas M1–M5; rename canônico; emissor JSON com `as_of`, formula, numerator/denominator; testes de list identity; docs/strings críticas.

**OUT:** Atingir 95% de M2; discovery de fontes; scheduler.

## Acceptance Criteria

1. **AC1 — Rename**  
   **Given** código/docs/JSON novos de coverage,  
   **When** a métrica de sinal comercial é emitida,  
   **Then** o campo canônico é `entities_with_recent_commercial_signal` (alias deprecado opcional por 1 sprint).

2. **AC2 — Dual emit**  
   **Given** a calculadora/contrato,  
   **When** gera manifesto de coverage,  
   **Then** inclui ao menos M1 e o slot M2 (`operational_source_coverage`) mesmo se M2 for `null`/`unmeasured` com motivo.

3. **AC3 — Denominador**  
   **Given** universo 200 km,  
   **When** qualquer % é calculado,  
   **Then** `denominator == 1093` (ou live count da mesma definição) e `do_not_change_denominator: true`.

4. **AC4 — List identity**  
   **Given** conjuntos covered/uncovered,  
   **When** valida identidade,  
   **Then** `|covered| + |uncovered| = denominator` e `|covered| = numerator` (fixture sessão 116).

5. **AC5 — Provenance fields**  
   **Given** output JSON,  
   **When** métrica é serializada,  
   **Then** contém `as_of`, `formula` ou `definition`, `source_artifacts` (lista).

## Fontes de dados

- `docs/ops/session-2026-07-17/coverage_canonical.json` (fixture/baseline)
- `sc_public_entities` (denominador)
- Evidence ledger / entity_coverage (quando disponível)

## Dependências

- Nenhuma de código bloqueante; alinha ADR-018.

## Riscos

| Risco | Mitigação |
|-------|-----------|
| Quebrar consumidores do nome legado | Alias + deprecation warning |
| M2 unmeasured parecer “0%” | Usar null + reason, não 0 silencioso |

## Testes requeridos

- Unit: rename keys, denominador fixo, identity 116
- Contract: JSON schema mínimo M1/M2
- Regressão: não reportar single-metric headline em emitter novo

## Evidência

- Output sample em `output/coverage/` (gitignored) + stamp opcional docs/ops
- pytest verde nos testes do contrato

## Definition of Done

- [ ] AC1–AC5 atendidos
- [ ] ADR-018 referenciado no módulo
- [ ] File list atualizado
- [ ] Sem raw dumps commitados (ADR-020)

## Comandos de validação

```bash
pytest tests/ -k "coverage_contract or commercial_signal or list_identity" -v
python -c "import json; d=json.load(open('docs/ops/session-2026-07-17/coverage_canonical.json')); assert d['commercial_numerator']==116; assert d['denominator']==1093"
# Após impl: CLI/módulo que emite entities_with_recent_commercial_signal
```

## File List (dev preenche)

- (a definir na implementação)

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Story criada — InProgress |
