# PE-K3-01 — Schema e semântica canônica de contratos

Status: InReview  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: K3.1  
Risk: HIGH-RISK  
Priority: P1

## Story

Como data engineer, quero fechar schema e semântica canônica de contratos, para preparar backfill de 3 anos sem ambiguidade de valores.

## Acceptance Criteria

1. **Given** migrations e código de contratos, **when** auditoria, **then** documento lista tabelas/colunas e semântica estimado/homologado/contratado/pago.
2. **Given** divergências schema×código, **when** encontradas, **then** listadas com severidade (não escondidas).

## File List

- `docs/baseline/k3-contract-schema-semantics.md`

## Dev Notes (2026-07-16)

- Entregue `docs/baseline/k3-contract-schema-semantics.md`.
- Semântica canônica: ESTIMADO / HOMOLOGADO / CONTRATADO / PAGO em `scripts/lib/value_semantics.py`.
- Divergências P0: `valor_total` vs `valor_global`; IDs de contrato; datas de vigência.
- Unificação física de schema adiada (data-engineer + architect).

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| 2026-07-16 | @dev | Baseline K3 schema/semântica; status → InReview |
