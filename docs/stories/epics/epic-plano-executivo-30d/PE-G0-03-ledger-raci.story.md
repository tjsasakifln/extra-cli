# PE-G0-03 — Ledger de evidências + RACI kick-off

Status: Ready  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: G0.4, G0.5  
Risk: STANDARD  
Priority: P0

## Story

Como PO, quero um ledger de evidências por requisito DoD e um RACI de kick-off, para rastrear aceite sem depender de histórico de chat.

## Acceptance Criteria

1. **Given** DoD com 1340 itens, **when** ledger é criado, **then** existe estrutura em `docs/ops/ledger/` com índice por seção e template de evidência.
2. **Given** plano RACI, **when** kick-off é documentado, **then** `docs/ops/ledger/raci-kickoff.md` define papéis Tiago/PO/Dev/QA/Data/DevOps e critérios de escalonamento.
3. **Given** GATE-0, **when** G0.1–G0.5 completos, **then** manifesto GATE-0 é publicado.

## File List

- `docs/ops/ledger/README.md`
- `docs/ops/ledger/evidence-index.md`
- `docs/ops/ledger/raci-kickoff.md`
- `docs/ops/ledger/GATE-0-BASELINE-LOCKED.md`
