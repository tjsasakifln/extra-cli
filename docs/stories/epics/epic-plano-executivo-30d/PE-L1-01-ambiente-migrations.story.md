# PE-L1-01 — Ambiente limpo + fresh migrations

Status: Ready  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: L1.1, L1.3  
Risk: HIGH-RISK  
Priority: P0

## Story

Como dev, quero provar ambiente local limpo e fresh install das migrations no HEAD, para fechar pré-requisitos da fundação local.

## Acceptance Criteria

1. **Given** pré-requisitos documentados, **when** validação roda, **then** relatório confirma Python, Docker/Postgres, env vars mínimas.
2. **Given** banco limpo ou recriável, **when** migrations aplicam, **then** todas as migrations do HEAD aplicam com exit 0 e contagem registrada.
3. **Given** schema, **when** validação, **then** tabelas canônicas críticas existem (documentadas na evidência).

## File List

- `docs/baseline/l1-env-prereqs.md`
- `docs/baseline/l1-fresh-migrations.md`
