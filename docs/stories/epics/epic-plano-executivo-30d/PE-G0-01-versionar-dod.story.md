# PE-G0-01 — Versionar DoD/plano e registrar autoridade

Status: Ready  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: G0.1  
Risk: STANDARD  
Priority: P0

## Story

Como dono do projeto, quero `DOD.md` e `extra-consultoria-plano-executivo.html` versionados na raiz com autoridade explícita, para que toda evolução use a mesma Definition of Done.

## Acceptance Criteria

1. **Given** os arquivos na working tree, **when** a story conclui, **then** `DOD.md` e `extra-consultoria-plano-executivo.html` estão commitados na branch da campanha.
2. **Given** o DoD §1, **when** o documento é versionado, **then** o item "Este arquivo está versionado na raiz" pode ser marcado com evidência de commit.
3. **Given** o plano HTML, **when** G0.1 é concluído, **then** o status da task G0.1 deixa de ser `blocked` e a evidência registra o path + commit.

## Scope

**IN:** versionar arquivos, registrar autoridade em docs da epic, atualizar status G0.1 no HTML.  
**OUT:** marcar gates LOCAL_READY/PROJECT_DONE; implementar cobertura.

## Tasks

- [ ] Commitar `DOD.md` e `extra-consultoria-plano-executivo.html`
- [ ] Documentar autoridade no epic/ledger
- [ ] Atualizar status G0.1 no HTML ep-data (se possível nesta story)

## Definition of Done

- [ ] Arquivos na raiz versionados
- [ ] Evidência de commit no ledger
- [ ] State file AIOX atualizado

## File List

- `DOD.md`
- `extra-consultoria-plano-executivo.html`
- `docs/stories/epics/epic-plano-executivo-30d/*`
