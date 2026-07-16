# PE-G0-02 — Rebaseline HEAD + freeze escopo/claims

Status: InReview  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: G0.2, G0.3  
Risk: HIGH-RISK  
Priority: P0

## Story

Como PO/QA, quero um rebaseline do HEAD e o freeze da meta 95% (editais e contratos separados), para eliminar narrativa de progresso sem evidência e resolver o conflito 80%×95%.

## Acceptance Criteria

1. **Given** HEAD atual, **when** rebaseline roda, **then** existe relatório em `docs/baseline/` com: commits recentes, estado de stories, métricas de cobertura conhecidas, gaps vs DoD.
2. **Given** EPIC-COVERAGE-MAX-200KM meta >80%, **when** freeze de escopo, **then** documento registra que **DoD 95% é autoridade** salvo decisão formal contrária de Tiago.
3. **Given** claims do README/handoffs, **when** auditoria de linguagem, **then** claims sem evidência no HEAD ficam listados como não permitidos.

## Scope

**IN:** docs de baseline, decisão de meta, matriz proposta×capacidade.  
**OUT:** implementação de crawlers; mudança de código de produção salvo docs.

## Tasks

- [x] Rebaseline HEAD → `docs/baseline/rebaseline-2026-07-16.md`
- [x] Freeze escopo/claims → `docs/baseline/scope-freeze-95.md`
- [x] Registrar R-02 (conflito 80×95) como resolvido em favor do DoD

## File List

- `docs/baseline/rebaseline-2026-07-16.md`
- `docs/baseline/scope-freeze-95.md`
- `.aiox/state/stories/PE-G0-02.json`

## Change Log

| Data | Agente | Alteração |
|------|--------|-----------|
| 2026-07-16 | @dev | Implementação G0.2+G0.3; status Ready→InReview; tasks concluídas; sem push; sem aceite DoD de cobertura |
