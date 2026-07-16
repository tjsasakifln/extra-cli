# PE-C2-01 — Fórmulas cobertura + success_zero/freshness

Status: InReview  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: C2.1, C2.2  
Risk: HIGH-RISK  
Priority: P0

## Story

Como data engineer, quero formalizar fórmulas de cobertura 95% por capability e garantir success_zero/freshness fail-closed, para métricas honestas.

## Acceptance Criteria

1. **Given** DoD §4.1, **when** documentação/código, **then** fórmulas de editais e contratos são separadas e ≥95% é o gate.
2. **Given** success_zero, **when** paginação incompleta, **then** não conta como coberto (teste ou prova de código).
3. **Given** freshness, **when** dado stale, **then** gate falha fechado.

## File List

- `docs/baseline/c2-coverage-formulas.md`
- `docs/baseline/c2-success-zero-freshness.md`
- possíveis ajustes em `scripts/coverage_*.py`, `scripts/freshness_gate.py`

## Dev Notes (2026-07-16)

- Entregue documentação em `docs/baseline/c2-coverage-formulas.md` e `docs/baseline/c2-success-zero-freshness.md`.
- Código de produção **não** alterado (gaps de gate são HIGH-RISK).
- DoD: 95% por capability; `consulting_readiness.DEFAULT_THRESHOLD=0.95`; `coverage_gate` 80% é **line coverage**.
- success_zero: prova em `states.py` + CHECK migrations 025b/029 + testes listed nos docs.
- freshness_gate: fail-closed exit 2; gap SLA contratos 24d vs DoD 7d.

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-16 | @dev | Baseline docs C2; status → InReview |
