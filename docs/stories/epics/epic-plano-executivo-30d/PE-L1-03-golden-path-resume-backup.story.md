# PE-L1-03 — Golden path + idempotência + backup/restore

Status: Ready  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: L1.5, L1.6, L1.7  
Risk: HIGH-RISK  
Priority: P0

## Story

Como dev/QA, quero reproduzir golden path no HEAD, provar resume/idempotência/DLQ e executar backup→restore local, para GATE-1.

## Acceptance Criteria

1. **Given** HEAD, **when** `python scripts/golden_path.py` (ou skip-network se DB offline com evidência), **then** ledger/exit code e artefatos documentados.
2. **Given** módulos DLQ/watermark/resume, **when** smoke tests, **then** testes unitários de resume/DLQ passam.
3. **Given** scripts de backup, **when** backup e restore de teste, **then** log prova execução real (ou BLOCKED se DB indisponível, com causa).

## File List

- `docs/baseline/l1-golden-path-head.md`
- `docs/baseline/l1-resume-dlq-smoke.md`
- `docs/baseline/l1-backup-restore.md`
- `output/golden-path/*` (se gerado)
